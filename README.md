# executionbackup-commercial

executionbackup is a load-balancing proxy to balance requests to multiple execution nodes.
executionbackup-commercial lets multiple commerical clients (think user wallets) to connect to execution nodes and get requests from them. executionbackup-commercial will get a majority response from execution nodes and return it to the client, assuring that the client does not get different responses for the same requests. (similar to Alchemy's Supernode) executionbackup-commercial also provides statistics about client's requests which are sent to a postgres database.

It have been tested and are working on Phase 0, as well as on merged testnets (kiln).

## Running

First, clone the repository, and install dependencies:

```bash
git clone https://github.com/tennisbowling/executionbackup-commercial.git
cd executionbackup-commercial
python3 -m pip install -r requirements.txt
```

Then, run it:

## TODO: include how to setup database and run


## Support
Contact me on discord at TennisBowling#7174
