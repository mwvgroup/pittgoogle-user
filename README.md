# pittgoogle-user

## Overview:
The Pitt-Google Broker is a cloud-based alert distribution service designed to provide near real-time processing of data from large-scale astronomical surveys like the [Legacy Survey of Space and Time](https://www.lsst.org). For its participation in the [DESC ELAsTiCC Challenge](https://portal.nersc.gov/cfs/lsst/DESC_TD_PUBLIC/ELASTICC/), the Pitt-Google Broker team developed this repo to process and classify alerts streamed by ELAsTiCC. Alerts are ingested into the data pipeline and classified using [SuperNNova](https://supernnova.readthedocs.io/en/latest/index.html). Supernovae classifications are published to a Pub/Sub topic and subsequently stored in BigQuery.

The deployment script in this repo can be used to create and delete some of the aforementioned Google Cloud Platform resources:

* A Pub/Sub subscription: 
    * Used to trigger a Cloud Run instance
* A container image of the classifier module, which is then deployed using Cloud Run
* A Pub/Sub topic:
    * Used to write SuperNNova classifications to a BigQuery table
* A BigQuery dataset & table:
    * Used to store SuperNNova classifications

## How to use the deployment script
* Begin a new terminal and confirm that your current directory is the same as the classifier's root directory (e.g., pittgoogle-user/SuperNNova).
* Initialize the following variables:

    ```
    testid="<enter testid name>" (default: test)

    survey="enter survey name"

    teardown="<enter False>" (default: False)

    trigger_topic="<enter trigger topic name>" (default: elasticc-alerts)

    trigger_topic_project="<enter trigger topic project name>" (default: avid-heading-329016)
    ```


* NOTE: If a Cloud Run instance already exists, selecting `teardown="True"` will delete all GCP resources associated with the information provided above.


* To call the deployment script, enter the following command:
    ```
    ./setup.sh "$testid" "$survey" "$teardown" "$trigger_topic" "$trigger_topic_project"
    ```
    * As the deployment script executes, a series of messages will appear. These messages will describe the status of deployment.


* Once the deployment script has successfully created your Cloud Run instance, you can review its status, and the status of other instances on the [Google Cloud Console](https://console.cloud.google.com/run?). Verify that the number of requests per second (Req/sec) is non-zero.

## How to stop a Cloud Run module
* Cloud Run instances are triggered by a Pub/Sub subcription. To stop a Cloud Run instance without deleting it, delete the trigger subscription. This can be done on the [Google Cloud Console](https://console.cloud.google.com/cloudpubsub/subscription/list?) or on the command line using: `gcloud pubsub subscriptions delete <enter subscription name>`.

* To view which subscription is triggering your Cloud Run instance, select your instance from the [Google Cloud Console](https://console.cloud.google.com/run?) and locate the _Triggers_ tab (it is located under the _URL_ section).

## How to delete a Cloud Run instance & all associated GCP resources
* The procedure follows the first few steps of this tutorial. Begin a new terminal and initialize the same variables. This time, select `teardown="True"`

* Confirm that your current directory is the same as the repo's root directory, and use the command `./setup.sh "$testid" "$survey" "$teardown" "$trigger_topic" "$trigger_topic_project"` to delete all the GCP resources associated with the information you provided (e.g., `testid`, `survey`, `trigger_topic`, etc.).
