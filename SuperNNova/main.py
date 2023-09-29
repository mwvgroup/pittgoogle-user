#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

"""Classify alerts using SuperNNova (M¨oller & de Boissi`ere 2019)."""

import os
from datetime import datetime, timezone
from pathlib import Path

import flask
import google.cloud.logging
import numpy as np
import pandas as pd
import pittgoogle
from supernnova.validation.validate_onthefly import classify_lcs

# connect the python logger to the google cloud logger
# by default, this captures INFO level and above
# pittgoogle uses the python logger
# we don't currently use the python logger directly in this script, but we could
# [TODO] make sure this is actually working
google.cloud.logging.Client().setup_logging()

PROJECT_ID = os.getenv("GCP_PROJECT")
TESTID = os.getenv("TESTID")
SURVEY = os.getenv("SURVEY")

# classifier
CLASSIFIER_NAME = "supernnova"
model_dir_name = "ZTF_DMAM_V19_NoC_SNIa_vs_CC_forFink"
model_file_name = "vanilla_S_0_CLF_2_R_none_photometry_DF_1.0_N_global_lstm_32x2_0.05_128_True_mean.pt"
MODEL_PATH = Path(__file__).resolve().parent / model_dir_name / model_file_name

# incoming
SCHEMA_IN = "elasticc.v0_9_1.alert"  # view the schema: pittgoogle.Schemas.get(SCHEMA_IN).avsc

# outgoing
HTTP_204 = 204  # http code: success (no content)
HTTP_400 = 400  # http code: bad request
SCHEMA_OUT = "elasticc.v0_9_1.brokerClassification"  # view the schema: pittgoogle.Schemas.get(SCHEMA_OUT).avsc
TABLE = pittgoogle.Table.from_cloud(CLASSIFIER_NAME, survey=SURVEY, testid=TESTID)
TOPIC = pittgoogle.Topic.from_cloud("SuperNNova", survey=SURVEY, testid=TESTID, projectid=PROJECT_ID)


app = flask.Flask(__name__)


@app.route("/", methods=["POST"])
def index():
    """Classify alert; publish and store results.

    This function is intended to be triggered by Pub/Sub messages, via Cloud Run.
    """
    # the module runs on Cloud Run as an HTTP endpoint
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


def _classify(alert: pittgoogle.Alert) -> dict:
    """Classify the alert using SuperNNova."""
    # init
    snn_df = _format_for_classifier(alert)
    device = "cpu"

    # classify
    _, pred_probs = classify_lcs(snn_df, MODEL_PATH, device)

    # extract results to a dict that matches the TABLE schema (TABLE.table.schema)
    # use `.item()` to convert numpy -> python types for later serialization
    pred_probs = pred_probs.flatten()
    classifications = {
        "alertId": alert.alertid,
        "diaObjectId": alert.objectid,
        "diaSourceId": alert.sourceid,
        "prob_class0": pred_probs[0].item(),
        "prob_class1": pred_probs[1].item(),
        "predicted_class": np.argmax(pred_probs).item(),
        "timestamp": datetime.now(timezone.utc),
    }

    return classifications


def _format_for_classifier(alert: pittgoogle.Alert) -> pd.DataFrame:
    """Create a DataFrame for input to SuperNNova."""
    alert_df = alert.dataframe
    snn_df = pd.DataFrame(
        data={
            # select a subset of columns and rename them for SuperNNova
            # get_key returns the name that the survey uses for a given field
            # for the full mapping, see alert.schema.map
            "FLT": alert_df[alert.get_key("filter")],
            "FLUXCAL": alert_df[alert.get_key("flux")],
            "FLUXCALERR": alert_df[alert.get_key("fluxerr")],
            "MJD": alert_df[alert.get_key("mjd")],
            # add the object ID
            "SNID": [alert.objectid] * len(alert_df.index),
        },
        index=alert_df.index,
    )
    return snn_df


def _create_outgoing_alert(alert_in: pittgoogle.Alert, results: dict) -> pittgoogle.Alert:
    """Combine the incoming alert with the classification results to create the outgoing alert."""
    # need to convert the broker ingest timestamp to conform with SCHEMA_OUT
    # occasionally a Pub/Sub timestamp doesn't include microseconds, so we need a try/except
    broker_ingest_time = alert_in.msg.publish_time.replace("Z", "+00:00")
    try:
        broker_ingest_time = datetime.strptime(broker_ingest_time, "%Y-%m-%dT%H:%M:%S.%f%z")
    except ValueError:
        broker_ingest_time = datetime.strptime(broker_ingest_time, "%Y-%m-%dT%H:%M:%S%z")

    # write down the mappings between our classifications and the ELASTTIC taxonomy
    # https://github.com/LSSTDESC/elasticc/blob/main/taxonomy/taxonomy.ipynb
    classifications = [
        {"classId": 2222, "probability": results["prob_class0"]},
    ]

    # construct a dict that conforms to SCHEMA_OUT
    outgoing_dict = {
        "alertId": alert_in.alertid,
        "diaSourceId": alert_in.sourceid,
        "elasticcPublishTimestamp": int(alert_in.attributes["kafka.timestamp"]),
        "brokerIngestTimestamp": broker_ingest_time,
        "brokerName": "Pitt-Google Broker",
        "brokerVersion": "v0.6",
        "classifierName": "SuperNNova_v1.3",
        "classifierParams": str(MODEL_PATH),  # record the training file
        "classifications": classifications,
    }

    # create the outgoing Alert
    # typically the pitt-google broker adds the IDs to the alert attributes
    # however, we're receiving alerts directly from the broker's consumer so the IDs are not yet attached
    # let's add them. these are not currently used but may help downstream users.
    alert_in.add_id_attributes()
    alert_out = pittgoogle.Alert.from_dict(
        payload=outgoing_dict, attributes=alert_in.attributes, schema_name=SCHEMA_OUT
    )
    # also add the predicted class to the attributes
    # again, not currently used, but is good practice and may help downstream users
    alert_out.attributes[CLASSIFIER_NAME] = results["predicted_class"]

    return alert_out
