# pittgoogle-examples

This repo contains code examples that access and process data from the Pitt-Google astronomical alert broker.
It currently contains two classifier modules that, when deployed to Cloud Run, listen to an alert stream, classify incoming alerts in real time, store their results in a BigQuery table, and publish their results to a dedicated Pub/Sub stream.
The outgoing classifications can then be accessed from BigQuery or Pub/Sub in a variety of ways.

[Demo: Deploy the SuperNNova Cloud Run Module](tutorial-notebooks/deploy-supernnova-module.md)

<https://link-to-pittgoogle-client-docs>
<https://link-to-cloud-run>
