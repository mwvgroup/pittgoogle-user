#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${1:-test}"
teardown="${2:-False}"
survey="${3:-elasticc}"
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"

# GCP resources used in this script
alerts_table="SuperNNova"
bq_dataset="${PROJECT_ID}:${survey}_alerts"
pubsub_SuperNNova_topic="${survey}-SuperNNova"
pubsub_trigger_topic="${survey}-alerts"
route="/"
runinvoker_svcact="cloud-run-invoker@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
subscrip="elasticc-loop" #used to trigger Cloud Run module
topic="elasticc-loop"
topic_project="avid-heading-329016"

if [ "$testid" != "False" ]; then
    pubsub_trigger_topic="${pubsub_trigger_topic}-${testid}"
    pubsub_SuperNNova_topic="${pubsub_SuperNNova_topic}-${testid}"
    bq_dataset="${bq_dataset}_${testid}"
    subscrip="elasticc-loop-${testid}"
fi

# create BigQuery, Pub/Sub resources
if [ "${teardown}" != "True" ]; then
    echo "Configuring BigQuery, Pub/Sub resources for Cloud Run..."
    # create pub/sub topics and subscriptions
    gcloud pubsub topics create "${pubsub_trigger_topic}"
    gcloud pubsub topics create "${pubsub_SuperNNova_topic}"

    # create the BigQuery dataset and table
    bq mk --dataset "${bq_dataset}"
    bq mk --table "${bq_dataset}.${alerts_table}" "templates/bq_${survey}_${alerts_table}_schema.json"

    # Deploy Cloud Run
    echo "Creating container image and deploying to Cloud Run..."
    moduledir="classifier"  # assumes we're in the repo's root dir
    config="${moduledir}/cloudbuild.yaml"
    # gcloud builds submit --config="${config}" \
    #     --substitutions=_SURVEY="${survey}",_TESTID="${testid}" \
    #     "${moduledir}"
    url=$(gcloud builds submit --config="${config}" \
        --substitutions=_SURVEY="${survey}",_TESTID="${testid}" \
        "${moduledir}" | grep "Service [^ ]* is running" | awk '{print $2}')
    
    echo "Creating trigger subscription for Cloud Run"
    gcloud pubsub subscriptions create "${subscrip}" \
        --topic "${topic}" \
        --topic-project "${topic_project}" \
        --ack-deadline=600 \
        --push-endpoint="${url}${route}" \
        --push-auth-service-account="${runinvoker_svcact}"

else
    # ensure that we do not teardown production resources
    if [ "${testid}" != "False" ]; then
        echo "Removing BigQuery, Pub/Sub resources for Cloud Run..."
        gcloud pubsub topics delete "${pubsub_trigger_topic}"
        gcloud pubsub topics delete "${pubsub_SuperNNova_topic}"
        gcloud pubsub subscriptions delete "${subscrip}" #needed to stop the Cloud Run module
        bq rm --table "${bq_dataset}.${alerts_table}"
        bq rm --dataset true "${bq_dataset}"
    fi
fi
