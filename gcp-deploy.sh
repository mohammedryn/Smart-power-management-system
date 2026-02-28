#!/bin/bash
# GridGuard GCP Compute Engine Deployment Script
# This script provisions an e2-micro Google Compute Engine instance (Free Tier eligible),
# opens the HTTP firewall, and uses a startup script to install Docker and run the app.

# --- CONFIGURATION ---
PROJECT_ID="your-gcp-project-id" # Replace with your GCP project ID
INSTANCE_NAME="gridguard-server"
ZONE="us-central1-a"
MACHINE_TYPE="e2-micro"

echo "🚀 Starting GridGuard Automated GCP Deployment..."

# 1. Ensure gcloud is pointing to the right project
gcloud config set project $PROJECT_ID

# 2. Create the firewall rule to allow web traffic (Port 80 and 5000)
echo "🛡️ Configuring Firewall rules..."
gcloud compute firewall-rules create allow-http-5000 \
    --action=ALLOW \
    --rules=tcp:80,tcp:5000 \
    --source-ranges=0.0.0.0/0 \
    --target-tags=http-server

# 3. Create the Compute Engine Instance with a startup script
echo "🖥️ Provisioning Compute Engine VM ($MACHINE_TYPE) in $ZONE..."
gcloud compute instances create $INSTANCE_NAME \
    --zone=$ZONE \
    --machine-type=$MACHINE_TYPE \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --tags=http-server \
    --metadata=startup-script="#!/bin/bash
echo 'Starting GridGuard Initialization...'
apt-get update
apt-get install -y git docker.io docker-compose

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Clone the project repository (Replace with your actual public repo URL)
cd /opt
git clone https://github.com/mohammedryn/digikey-hackathon-submission.git gridguard
cd gridguard/backend

# NOTE: The user must manually SSH into the instance to create the .env file 
# with their Gemini and Telegram API keys before running docker-compose up.
echo 'Initialization complete. Waiting for .env configuration.'
"

echo "✅ Deployment infrastructure provisioned!"
echo "--------------------------------------------------------"
echo "NEXT STEPS:"
echo "1. Get your VM's External IP from the GCP Console."
echo "2. SSH into your new VM: gcloud compute ssh $INSTANCE_NAME --zone=$ZONE"
echo "3. Navigate to the app directory: cd /opt/gridguard/backend"
echo "4. Create your .env file: nano .env (Add GEMINI_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID)"
echo "5. Start the server: sudo docker-compose up -d"
echo "6. Access your dashboard at: http://<EXTERNAL_IP>"
echo "--------------------------------------------------------"
