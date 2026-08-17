#!/bin/bash
# scripts/deploy.sh
# Deployment script to package DataLens as a Docker container and deploy to Google Cloud Run.
# The Parquet warehouse will be hosted on Google Cloud Storage (GCS).

set -e

PROJECT_ID="your-gcp-project-id"
REGION="us-central1"
SERVICE_NAME="datalens-app"
IMAGE_NAME="gcr.io/$PROJECT_ID/$SERVICE_NAME"
BUCKET_NAME="gs://$PROJECT_ID-datalens-warehouse"

echo "====================================================="
echo " Deploying DataLens to Google Cloud Run"
echo "====================================================="

echo "[1/4] Preparing Google Cloud Storage bucket for Parquet warehouse..."
if ! gsutil ls "$BUCKET_NAME" > /dev/null 2>&1; then
    gsutil mb -l $REGION "$BUCKET_NAME"
    echo "Bucket $BUCKET_NAME created."
else
    echo "Bucket $BUCKET_NAME already exists."
fi

# Upload the initial raw Parquet data to the GCS bucket
echo "Uploading initial Parquet dataset to GCS..."
gsutil rsync -r data/raw/ "$BUCKET_NAME/raw/"
gsutil rsync -r data/processed/ "$BUCKET_NAME/processed/"

echo "[2/4] Building Docker image for the Streamlit app..."
# Assuming a standard Dockerfile exists in the root directory
docker build -t "$IMAGE_NAME" .

echo "[3/4] Pushing image to Google Container Registry..."
docker push "$IMAGE_NAME"

echo "[4/4] Deploying to Google Cloud Run..."
gcloud run deploy $SERVICE_NAME \
    --image "$IMAGE_NAME" \
    --region $REGION \
    --platform managed \
    --allow-unauthenticated \
    --set-env-vars="DATALENS_GCS_BUCKET=$BUCKET_NAME,ENVIRONMENT=production" \
    --memory 2Gi \
    --cpu 1

echo "====================================================="
echo " Deployment Complete!"
echo " DataLens is now running and serving data directly from GCS."
echo "====================================================="
