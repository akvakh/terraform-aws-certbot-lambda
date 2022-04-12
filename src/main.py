#!/usr/bin/env python3

import os
import shutil
import boto3
import certbot.main
import re

# Let’s Encrypt acme-v02 server that supports wildcard certificates
CERTBOT_SERVER = 'https://acme-v02.api.letsencrypt.org/directory'

# Temp dir of Lambda runtime
CERTBOT_DIR = '/tmp/certbot'


def rm_tmp_dir():
    if os.path.exists(CERTBOT_DIR):
        try:
            shutil.rmtree(CERTBOT_DIR)
        except NotADirectoryError:
            os.remove(CERTBOT_DIR)


def obtain_certs(email, domains):
    certbot_args = [
        # Override directory paths so script doesn't have to be run as root
        '--config-dir', CERTBOT_DIR,
        '--work-dir', CERTBOT_DIR,
        '--logs-dir', CERTBOT_DIR,

        # Obtain a cert but don't install it
        'certonly',

        # Run in non-interactive mode
        '--non-interactive',

        # Agree to the terms of service
        '--agree-tos',

        # Email of domain administrator
        '--email', email,

        # Use dns challenge with route53
        '--dns-route53',
        '--preferred-challenges', 'dns-01',

        # Use this server instead of default acme-v01
        '--server', CERTBOT_SERVER,

        # Domains to provision certs for (comma separated)
        '--domains', domains,
    ]
    return certbot.main.main(certbot_args)


# /tmp/certbot
# ├── live
# │   └── [domain]
# │       ├── README
# │       ├── cert.pem
# │       ├── chain.pem
# │       ├── fullchain.pem
# │       └── privkey.pem
def upload_certs(s3_bucket, s3_prefix):
    client = boto3.client('s3')
    cert_dir = os.path.join(CERTBOT_DIR, 'live')
    for dirpath, _dirnames, filenames in os.walk(cert_dir):
        for filename in filenames:
            local_path = os.path.join(dirpath, filename)
            relative_path = os.path.relpath(local_path, cert_dir)
            s3_key = os.path.join(s3_prefix, relative_path)
            print(f'Uploading: {local_path} => s3://{s3_bucket}/{s3_key}')
            client.upload_file(local_path, s3_bucket, s3_key)

# def download_certs(s3_bucket, s3_prefix, domains):
#     client = boto3.client('s3')
#     cert_dir = os.path.join(CERTBOT_DIR, 'live')

# def check_existing_acm_cert(cert_arn,domains):
#     pass
## 
def update_acm(domains, cert_arn):
    client = boto3.client('acm')

    cert_dir = os.path.join(os.path.join(CERTBOT_DIR, 'live'), domains)
    cert_dir = re.sub("\.$", "", cert_dir)
    certificate=open(os.path.join(cert_dir, 'cert.pem'), 'rb').read()
    privatekey=open(os.path.join(cert_dir, 'privkey.pem'), 'rb').read()
    chain=open(os.path.join(cert_dir, 'chain.pem'), 'rb').read()


    if (cert_arn == '*'):
        response = client.import_certificate(
            Certificate=certificate,
            PrivateKey=privatekey,
            CertificateChain=chain
        )
    else:
        response = client.import_certificate(
            CertificateArn=cert_arn,
            Certificate=certificate,
            PrivateKey=privatekey,
            CertificateChain=chain
        )

    print(response)
    print('Certificates uploaded to ACM suceessfully')
    

def guarded_handler(event, context):
    # Contact email for LetsEncrypt notifications
    email = os.environ.get('EMAIL')
    # Domains that will be included in the certificate
    domains = os.environ.get('DOMAINS')
    # The S3 bucket to publish certificates
    s3_bucket = os.environ.get('S3_BUCKET')
    # The S3 key prefix to publish certificates
    s3_prefix = os.environ.get('S3_PREFIX')
    # Certificate ARN in ACM to update to 
    cert_arn = os.environ.get('CERT_ARN')

    obtain_certs(email, domains)
    upload_certs(s3_bucket, s3_prefix)
    update_acm(domains, cert_arn)

    return 'Certificates obtained and uploaded successfully.'


def lambda_handler(event, context):
    try:
        rm_tmp_dir()
        return guarded_handler(event, context)
    finally:
        rm_tmp_dir()
