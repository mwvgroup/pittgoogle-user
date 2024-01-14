#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Classify alerts using MicroLIA (Goodines et al. 2020, https://arxiv.org/abs/2004.14347)."""

import os
from datetime import datetime, timezone
from pathlib import Path

import flask
import google.cloud.logging
import numpy as np
import pittgoogle

from MicroLIA import classify_lcs

# connect the python logger to the google cloud logger
# by default, this captures INFO level and above
# pittgoogle uses the python logger
# we don't currently use the python logger directly in this script, but we could
# [TODO] make sure this is actually working
google.cloud.logging.Client().setup_logging()

PROJECT_ID = os.getenv("GCP_PROJECT")
TESTID = os.getenv("TESTID")
SURVEY = os.getenv("SURVEY")

BROKER_NAME = "Pitt-Google Broker"
MODULE_NAME = "microlia"
MODULE_VERSION = "v0.6"

# classifier
CLASSIFIER_NAME = "MicroLIA_v2.6"  # include the version
model_dir_name = "trained_model"
model_file_name = "MicroLIA_ensemble_model"
MODEL_PATH = Path(__file__).resolve().parent / model_dir_name / model_file_name

# incoming
# a url route is used in setup.sh when the trigger subscription is created
# it is possible to define multiple routes in a single module and trigger them using different subscriptions
ROUTE_RUN = "/"  # url route that will trigger run()
SCHEMA_IN = "elasticc.v0_9_1.alert"  # view the schema: pittgoogle.Schemas.get(SCHEMA_IN).avsc

# outgoing
HTTP_204 = 204  # http code: success (no content)
HTTP_400 = 400  # http code: bad request
SCHEMA_OUT = "elasticc.v0_9_1.brokerClassification"  # view the schema: pittgoogle.Schemas.get(SCHEMA_OUT).avsc
# pittgoogle will construct the full resource names from the MODULE_NAME, SURVEY, and TESTID
TABLE = pittgoogle.Table.from_cloud(MODULE_NAME, survey=SURVEY, testid=TESTID)
TOPIC = pittgoogle.Topic.from_cloud(MODULE_NAME, survey=SURVEY, testid=TESTID, projectid=PROJECT_ID)


app = flask.Flask(__name__)


@app.route(ROUTE_RUN, methods=["POST"])
def run():
    """Classify the alert; publish and store results.

    This module is intended to be deployed as a Cloud Run service. It will operate as an HTTP endpoint
    triggered by Pub/Sub messages. This function will be called once for every message sent to this route.
    It should accept the incoming HTTP request and return a response.

    Returns
    -------
    response : tuple(str, int)
        Tuple containing the response body (string) and HTTP status code (int). Flask will convert the
        tuple into a proper HTTP response. Note that the response is a status message for the web server
        and should not contain the classification results.
    """
    # extract the envelope from the request that triggered the endpoint
    # this contains a single Pub/Sub message with the alert to be processed
    envelope = flask.request.get_json()

    # unpack the alert. raises a `BadRequest` if the envelope does not contain a valid message
    try:
        alert = pittgoogle.Alert.from_cloud_run(envelope=envelope, schema_name=SCHEMA_IN)
    except pittgoogle.exceptions.BadRequest as exc:
        return str(exc), HTTP_400

    # classify
    classifications = _classify(alert)

    # publish
    TOPIC.publish(_create_outgoing_alert(alert, classifications))
    TABLE.insert_rows([classifications])

    return "", HTTP_204


def _classify(model, alert: pittgoogle.Alert) -> dict:
    """Classify the alert using MicroLIA."""
    # init
    df = alert.dataframe
    # get_key returns the name that the survey uses for a given field
    # for the full mapping, see alert.schema.map
    mjd = alert.get_key("mjd")
    flux, fluxerr = alert.get_key("flux"), alert.get_key("fluxerr")

    # classify
    prediction = model.predict(df[mjd], df[flux], df[fluxerr], convert=False)

    # prediction is going to be a 2D numpy array of [[pred_class, pred_prob], ...]
    # with both pred_class and pred_prob stored as floats
    # Get the highest probability and look up the pred_class
    most_likely_index = np.argmax(prediction[:, 1])
    most_likely = prediction[most_likely_index, 0]
    # Map to a dict from the 2D array to make later look ups easier
    classifications = {int(pc): pp for (pc, pp) in prediction}

    # extract results to a dict that matches the TABLE schema (TABLE.table.schema)
    # use `.item()` to convert numpy -> python types for later serialization
    classification_dict = {
        "alertId": alert.alertid,
        "diaObjectId": alert.objectid,
        "diaSourceId": alert.sourceid,
        "prob_class0": classifications[0].item(),
        "prob_class1": classifications[1].item(),
        "prob_class2": classifications[2].item(),
        "prob_class3": classifications[3].item(),
        "predicted_class": most_likely,
        "timestamp": datetime.now(timezone.utc),
    }

    return classification_dict


def _create_outgoing_alert(alert_in: pittgoogle.Alert, results: dict) -> pittgoogle.Alert:
    """Combine the incoming alert with the classification results to create the outgoing alert."""
    # Write down the mappings between our classifications
    # and the ELAsTiCC taxonomy
    # https://github.com/LSSTDESC/elasticc/blob/main/taxonomy/taxonomy.ipynb
    # I'm not really sure where CVs should be (prob_class0).
    # I'll put them under Periodic/Other (2321).
    classifications = [
        {"classId": 2321, "probability": results["prob_class0"]},
        {"classId": 2326, "probability": results["prob_class1"]},
        {"classId": 2235, "probability": results["prob_class2"]},
        {"classId": 2323, "probability": results["prob_class3"]},
    ]

    # construct a dict that conforms to SCHEMA_OUT
    outgoing_dict = {
        "alertId": alert_in.alertid,
        "diaSourceId": alert_in.sourceid,
        "elasticcPublishTimestamp": int(alert_in.attributes["kafka.timestamp"]),
        "brokerIngestTimestamp": alert_in.msg.publish_time,
        "brokerName": BROKER_NAME,
        "brokerVersion": MODULE_VERSION,
        "classifierName": CLASSIFIER_NAME,
        "classifierParams": str(MODEL_PATH),  # Record the training file
        "classifications": classifications,
    }

    # create the outgoing Alert
    alert_out = pittgoogle.Alert.from_dict(
        payload=outgoing_dict, attributes=alert_in.attributes, schema_name=SCHEMA_OUT
    )
    # add the predicted class to the attributes. may help downstream users filter messages.
    alert_out.attributes[MODULE_NAME] = results["predicted_class"]

    return alert_out
