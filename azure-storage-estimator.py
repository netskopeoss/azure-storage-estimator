import argparse
import sys
import json
import os
import pathlib
import csv
from datetime import datetime, timedelta
from azure.identity import ClientSecretCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.storage.blob import (BlobServiceClient,
        BlobClient,
        generate_account_sas,
        ResourceTypes,
        AccountSasPermissions)
from azure.mgmt.storage.models import (
    StorageAccountCreateParameters,
    StorageAccountUpdateParameters,
    Sku,
    SkuName,
    Kind
)
from azure.mgmt.subscription import SubscriptionClient
supported_account_types = ['BlobStorage', 'StorageV2']

def oprint(data='', **kwargs):
    if not options.quiet: print(data,**kwargs)

def ocsv(data):
    file_exts = {}
    csv       = []
    for account in data['subscription.storage_account']:
        for bucket in data['subscription.storage_account'][account]:
            for file_ext in data['subscription.storage_account'][account][bucket]['size.ext']:
                if file_ext not in file_exts:
                    file_exts[file_ext] = 0
                file_exts[file_ext] += 1

    for account in data['subscription.storage_account']:
        for bucket in data['subscription.storage_account'][account]:
            row = {'account':account, 'storage account':bucket}
            for file_ext in file_exts:
                if file_ext in data['subscription.storage_account'][account][bucket]['size.ext']:
                    row['bytes_'+file_ext]= data['subscription.storage_account'][account][bucket]['size.ext'][file_ext]
                else:
                    row['bytes_'+file_ext] = 0
            csv.append(row)
    return csv
    
def get_options():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--quiet", "-q", help="Suppress all output", action='store_true', default=False, required=False)
    parser.add_argument("--debug", "-d", help="Enable debugging mode", action='store_true', default=False, required=False)
    parser.add_argument("--config", "-c", help="Configuration JSON file with script options", metavar='FILE', type=str, required=False)
    parser.add_argument("--json", help="Output JSON file to write with results", metavar='FILE', type=str, required=False)
    parser.add_argument("--csv", help="Output CSV file to write with results", metavar='FILE', type=str, required=False)
    parser.add_argument("--test", "-t", help="Do not iteratively scan buckets for testing", action='store_true', default=False, required=False)
    parser.add_argument("--maxsize", "-x", help="Maximum size file allowed in scan", metavar='BYTES', type=int, default=33554432, required=False)
    parser.add_argument("--minsize", "-n", help="Minimum size file allowed in scan", metavar='BYTES', type=int, default=1, required=False)
    parser.add_argument("--allowext", "-a", help="List of extensions allowed in scan", metavar='EXT', type=str, nargs='+', default=[], required=False)
    parser.add_argument("--blockext", "-b", help="List of extensions excluded from scan", metavar='EXT', type=str, nargs='+', default=[], required=False)
    parser.add_argument("--include", "-i", help="List of subscriptions included in scan", metavar='ACCOUNTID', type=str, nargs='+', default=[], required=False)
    parser.add_argument("--exclude", "-e", help="List of subscriptions excluded from scan", metavar='ACCOUNTID', type=str, nargs='+', default=[], required=False)
    if len(sys.argv) < 2:
        parser.print_usage()
        sys.exit(1)

    args = parser.parse_args()

    # If we were provided a json config file, then start baseline arguments and override with file options
    if args.config and pathlib.Path(args.config).is_file():
        with open(args.config) as f:
                  json_args = json.load(f)
                  vargs = vars(args)
                  dargs = {**vargs, **json_args}
                  args  = argparse.Namespace(**dargs)

    return args

def list_blobs(sub_name, account_name, connection_string, account_url, blob_service, container_name, credential, filter_list):
    container_client = blob_service.get_container_client(container_name)
    try:
        blobs = container_client.list_blobs()
    except Exception as ex:
        file_stats['errors'].append("Couldn't get blobs of subscription:"+sub_name+" storage account:"+strorage_account+ "container:"+container_name+ "("+ str(ex)+")")
        pass

    for blob in blobs:
        file_extension = pathlib.Path(blob.name).suffix.strip('.').lower()
        if options.debug: oprint(str(blob.size)+" "+blob.name+" ("+file_extension+")")

        # Apply filters to file and move on if file properties do not match
        if blob.size > filter_list.maxsize:
            continue
        if blob.size < filter_list.minsize:
            continue
        if filter_list.allowext and file_extension not in filter_list.allowext:
            continue
        if filter_list.blockext and file_extension in filter_list.blockext:
            continue

        file_stats['total']['size'] += blob.size
        file_stats['total']['files'] += 1
        if file_extension not in file_stats['total']['size.ext']:
            file_stats['total']['size.ext'][file_extension] = 0
        if file_extension not in file_stats['total']['files.ext']:
            file_stats['total']['files.ext'][file_extension] = 0
        file_stats['total']['size.ext'][file_extension] += blob.size
        file_stats['total']['files.ext'][file_extension] += 1

        # Setup counters for per-account totals
        if file_extension not in file_stats['subscription'][sub_name]['size.ext']:
            file_stats['subscription'][sub_name]['size.ext'][file_extension] = 0

        if file_extension not in file_stats['subscription'][sub_name]['files.ext']:
            file_stats['subscription'][sub_name]['files.ext'][file_extension] = 0

        # Increment per-account counters
        file_stats['subscription'][sub_name]['size'] += blob.size
        file_stats['subscription'][sub_name]['files'] += 1
        file_stats['subscription'][sub_name]['size.ext'][file_extension] += blob.size
        file_stats['subscription'][sub_name]['files.ext'][file_extension] += 1

        # Setup counters for per-account, per-bucket totals
        if file_extension not in file_stats['subscription.storage_account'][sub_name][account_name]['size.ext']:
            file_stats['subscription.storage_account'][sub_name][account_name]['size.ext'][file_extension] = 0

        if file_extension not in file_stats['subscription.storage_account'][sub_name][account_name]['files.ext']:
            file_stats['subscription.storage_account'][sub_name][account_name]['files.ext'][file_extension] = 0

        # Increment per-account, per-bucket counters
        file_stats['subscription.storage_account'][sub_name][account_name]['size'] += blob.size
        file_stats['subscription.storage_account'][sub_name][account_name]['files'] += 1
        file_stats['subscription.storage_account'][sub_name][account_name]['size.ext'][file_extension] += blob.size
        file_stats['subscription.storage_account'][sub_name][account_name]['files.ext'][file_extension] += 1

def list_containers(sub_name, strorage_account, connection_string, credentials, filter_list):
    account_url = "https://" + strorage_account + ".blob.core.windows.net/"
    blob_service = BlobServiceClient(account_url=account_url, credential=credentials)
    try:
        containers = blob_service.list_containers()
        for container in containers:
            list_blobs(sub_name, strorage_account, connection_string, account_url, blob_service, container.name, credentials, filter_list)
    except Exception as ex:
        oprint("error occured {}".format(ex))
        file_stats['errors'].append("Couldn't get containers of subscription:"+sub_name+" storage account:"+strorage_account+"("+str(ex)+")")

if __name__ == "__main__":
    file_stats    = {'errors':[], 'total':{'size':0, 'files':0, 'size.ext':{}, 'files.ext':{}},'subscription': {}, 'subscription.storage_account':{}}
    options       = get_options()

    credentials = ClientSecretCredential(
        client_id=os.environ['AZURE_CLIENT_ID'],
        client_secret=os.environ['AZURE_CLIENT_SECRET'],
        tenant_id=os.environ['AZURE_TENANT_ID']
    )

    subscription_client = SubscriptionClient(credentials)
    try:
        subs = subscription_client.subscriptions.list()
    except Exception as ex:
        oprint("error occured {}".format(ex))
        file_stats['errors'].append("Couldn't list subscriptions +("+str(ex)+")")
        pass
    try:
        for sub in subs:
            # Skip accounts that are not in the inclusion list
            if options.include and sub.display_name not in options.include:
                continue

            # Skip accounts that are in the exclusion list
            if options.exclude and sub.display_name in options.exclude:
                continue

            oprint("Subscription: " + sub.display_name)

            file_stats['subscription'][sub.display_name] = {'size':0, 'files':0, 'size.ext':{}, 'files.ext':{}}
            file_stats['subscription.storage_account'][sub.display_name] = {}
            resource_client = ResourceManagementClient(credentials, sub.subscription_id)
            storage_client = StorageManagementClient(credentials, sub.subscription_id)

            # Retrieve the list of resource groups
            try:
                resource_group_list = resource_client.resource_groups.list()
            except Exception as ex:
                oprint("error occured {}".format(ex))
                file_stats['errors'].append("Couldn't get resource groups in subscription:"+sub.display_name+"("+str(ex)+")")
                pass

            for resource_group in resource_group_list:
                oprint("listing resource group {}".format(resource_group.name))
                storage_accounts_list = storage_client.storage_accounts.list_by_resource_group(resource_group.name)
                for account in storage_accounts_list:
                    if account.kind in supported_account_types:
                        try:
                            keys = storage_client.storage_accounts.list_keys(resource_group.name, account.name)
                        except Exception as ex:
                            file_stats['errors'].append("Couldn't get account keys in subscription:"+sub.display_name+"("+str(ex)+")")
                            continue
                        file_stats['subscription.storage_account'][sub.display_name][account.name] = {'size':0, 'files':0, 'size.ext':{}, 'files.ext':{}}
                        conn_string = f"DefaultEndpointsProtocol=https;EndpointSuffix=core.windows.net;AccountName={account.name};AccountKey={keys.keys[0].value}"
                        list_containers(sub.display_name, account.name, conn_string, keys.keys[1].value, options)
    except Exception as ex:
        oprint("error occured {}".format(ex))
        file_stats['errors'].append("Couldn't traverse subscriptions +("+str(ex)+")")
    if options.json:
        with open(options.json,'w') as outfile:
            json.dump(file_stats,outfile,indent=4,sort_keys=True)

    if options.csv:
        csv_data = ocsv(file_stats)
        if csv_data:
            with open(options.csv,'w') as outfile:
                writer = csv.DictWriter(outfile,fieldnames=csv_data[0].keys())
                writer.writeheader()
                for row in csv_data:
                    writer.writerow(row)
