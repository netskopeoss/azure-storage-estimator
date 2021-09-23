# azure-storage-estimator

```
usage: azure-storage-estimator.py [-h] [--quiet] [--debug] [--config FILE] [--json FILE] [--csv FILE]
                                  [--maxsize BYTES] [--minsize BYTES] [--allowext EXT [EXT ...]]
                                  [--blockext EXT [EXT ...]] [--include ACCOUNTID [ACCOUNTID ...]]
                                  [--exclude ACCOUNTID [ACCOUNTID ...]]

optional arguments:
  -h, --help            show this help message and exit
  --quiet, -q           Suppress all output
  --debug, -d           Enable debugging mode
  --config FILE, -c FILE
                        Configuration JSON file with script options
  --json FILE           Output JSON file to write with results
  --csv FILE            Output CSV file to write with results
  --maxsize BYTES, -x BYTES
                        Maximum size file allowed in scan
  --minsize BYTES, -n BYTES
                        Minimum size file allowed in scan
  --allowext EXT [EXT ...], -a EXT [EXT ...]
                        List of extensions allowed in scan
  --blockext EXT [EXT ...], -b EXT [EXT ...]
                        List of extensions excluded from scan
  --include ACCOUNTID [ACCOUNTID ...], -i ACCOUNTID [ACCOUNTID ...]
                        List of accounts included in scan
  --exclude ACCOUNTID [ACCOUNTID ...], -e ACCOUNTID [ACCOUNTID ...]
                        List of accounts excluded from scan

```

## Installing

Python3.6 or later is required

pip3 install -r requirements.txt

This script expects that Azure credentials are accessible to the Azure python module.

Export **AZURE_CLIENT_ID**, **AZURE_CLIENT_SECRET** and **AZURE_TENANT_ID** to the shell environment variables
The application must be run with an account that has **Storage Account Contributor Role**

## Running

With no options, this script will attach to the account with supplied credentials and 
look at every storage account in the subscription.  

It won't scan empty files or files bigger than 32MB by default.  The options --maxsize and --minsize will 
change this behavior.

In order to scan an entire organization, this script must run under the master account or 
a delegated account that can access AssumeRole for the each accounts IAM role OrganizationAccountAccessRole.

Output can be specified for JSON or CSV format.  To write a file use the --json /path/to/file.json or --csv /path/to/file.csv option.

This script will read a JSON configuration file of options, and several examples are in the config directory

## Examples

There is a folder called config with example JSON configurations
