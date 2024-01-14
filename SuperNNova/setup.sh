#!/usr/bin/env bash
# Create and configure GCP resources needed to deploy Cloud Run

# setup
testid="${1:-test}"
survey="${2:-elasticc}"
teardown="${3:-False}"
trigger_topic="${4:-elasticc-alerts}"
trigger_topic_project="${5:-avid-heading-329016}"

PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"  # env var associated with the user's credentials

MODULE_NAME="supernnova"  # lower case required by cloud run
ROUTE_RUN="/"  # url route that will trigger main.run()

#--- Make the user confirm the settings
echo
echo "setup.sh will run with the following configs: "
echo
echo "testid = ${testid}"
echo "survey = ${survey}"
echo "teardown = ${teardown}"
echo "trigger_topic = ${trigger_topic}"
echo "trigger_topic_project = ${trigger_topic_project}"
echo "GOOGLE_CLOUD_PROJECT = ${PROJECT_ID}"
echo
echo "Continue?  [y/(n)]: "

read input
input="${input:-n}"
if [ "${input}" != "y" ]; then
    echo "Exiting setup."
    echo
    exit
fi

# GCP resources & variables used in this script that need a testid
cr_module_name="${survey}-${MODULE_NAME}"  # lower case required by cloud run
ps_input_subscrip="${trigger_topic}"  # pub/sub subscription used to trigger cloud run module
bq_dataset="${PROJECT_ID}:${survey}"
ps_output_topic="${survey}-SuperNNova"  # desc is using this. leave camel case to avoid a breaking change

if [ "$testid" != "False" ]; then
    cr_module_name="${cr_module_name}-${testid}"
    ps_input_subscrip="${ps_input_subscrip}-${testid}"
    bq_dataset="${bq_dataset}_${testid}"  # "-" not allowed by bigquery so use "_"
    ps_output_topic="${ps_output_topic}-${testid}"
fi

# additional GCP resources & variables used in this script
module_image_name="gcr.io/${PROJECT_ID}/${cr_module_name}"
bq_table="${MODULE_NAME}"
region="us-central1"
runinvoker_svcact="cloud-run-invoker@${PROJECT_ID}.iam.gserviceaccount.com"

# create BigQuery, Pub/Sub resources
if [ "${teardown}" != "True" ]; then
    echo
    echo "Configuring BigQuery, Pub/Sub resources for Cloud Run..."

    # create pub/sub topics and subscriptions
    gcloud pubsub topics create "${ps_output_topic}"

    # create the BigQuery dataset and table
    bq mk --dataset "${bq_dataset}"
    bq mk --table "${bq_dataset}.${bq_table}" "bq_${survey}_${bq_table}_schema.json"

    # Deploy Cloud Run
    echo "Creating container image and deploying to Cloud Run..."
    moduledir="./"  # assumes deploying what's in our current directory
    config="${moduledir}/cloudbuild.yaml"
    url=$(gcloud builds submit --config="${config}" \
        --substitutions="_SURVEY=${survey},_TESTID=${testid},_MODULE_NAME=${cr_module_name}" \
        "${moduledir}" | sed -n 's/^Step #2: Service URL: \(.*\)$/\1/p')

    echo "Creating trigger subscription for Cloud Run..."
    # WARNING:  This is set to retry failed deliveries. If there is a bug in main.py this will
    # retry indefinitely, until the message is delete manually.
    gcloud pubsub subscriptions create "${ps_input_subscrip}" \
        --topic "${trigger_topic}" \
        --topic-project "${trigger_topic_project}" \
        --ack-deadline=600 \
        --push-endpoint="${url}${ROUTE_RUN}" \
        --push-auth-service-account="${runinvoker_svcact}"

else
    # ensure that we do not teardown production resources
    if [ "${testid}" != "False" ]; then
        echo "Removing BigQuery, Pub/Sub resources for Cloud Run..."
        gcloud pubsub subscriptions delete "${ps_input_subscrip}" # needed to stop the Cloud Run module
        gcloud pubsub topics delete "${ps_output_topic}"
        bq rm --table "${bq_dataset}.${bq_table}"
        bq rm --dataset=true "${bq_dataset}"
        gcloud run services delete "${cr_module_name}" --region "${region}"
        gcloud container images delete "${module_image_name}"
    fi
fi
