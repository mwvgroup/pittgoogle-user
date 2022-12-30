#!/usr/bin/env bash
# Setup tasks that need to be run once per Google Cloud project

# setup
PROJECT_ID="${GOOGLE_CLOUD_PROJECT}"

# get the project number. don't know why this is so cumbersome
PROJECT_NUMBER=$(gcloud projects list \
    --filter="$(gcloud config get-value project)" \
    --format="value(PROJECT_NUMBER)" \
    )

# enable APIs
gcloud services enable \
    bigquery.googleapis.com \
    iam.googleapis.com \
    pubsub.googleapis.com \
    run.googleapis.com


# read the following add-iam-policy-binding commands like this:
# gcloud <resourceType> add-iam-policy-binding <resourceName> \
    # --member=<accountToGrantOnTheResource> \
    # --role=<roleToGrantOnTheResource>
# credit: https://stackoverflow.com/questions/61875357/gcloud-confusion-around-add-iam-policy-binding


# Cloud Build needs to be able to do a bunch of things
# grant necessary permissions to the Build service account
build_svcact="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"
# Cloud Run Admin role
role="roles/run.admin"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${build_svcact}" \
    --role="${role}"
# permission to act as the runtime service account for Cloud Run, so it can deploy containers
run_svcact="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
role="roles/iam.serviceAccountUser"
gcloud iam service-accounts add-iam-policy-binding "${run_svcact}" \
    --member="serviceAccount:${build_svcact}" \
    --role="${role}"
# # permission to create Pub/Sub subscriptions
# role="roles/pubsub.admin"
# gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
#     --member="serviceAccount:${build_svcact}" \
#     --role="${role}"


# service account for Pub/Sub subscriptions to use to invoke cloud Run
runinvoker_name="cloud-run-invoker"
runinvoker_svcact="${runinvoker_name}@${GOOGLE_CLOUD_PROJECT}.iam.gserviceaccount.com"
runinvoker_dispname="Cloud Run Invoker"
runinvoker_descrip="Service account used by Pub/Sub push subscriptions to invoke Cloud Run."
gcloud iam service-accounts create "${runinvoker_name}" \
    --display-name "${runinvoker_dispname}" \
    --description "${runinvoker_descrip}"
# give it permissions
role="roles/run.invoker"
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${runinvoker_svcact}" \
    --role="${role}"
# run_service="classifier-testid"
# gcloud run services add-iam-policy-binding "${run_service}" \
#    --member="serviceAccount:${runinvoker_svcact}" \
#    --role="${role}"


# Allow Pub/Sub to create authentication tokens in the project
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
   --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-pubsub.iam.gserviceaccount.com" \
   --role="roles/iam.serviceAccountTokenCreator"
