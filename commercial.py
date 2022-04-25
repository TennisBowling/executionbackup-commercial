import executionbackup
from sanic import Sanic, response
from sanic.request import Request
from sanic.log import logger, Colors
from ujson import loads
from platform import python_version, system, release, machine
import argparse
import logging
from os import cpu_count
from psutil import Process
import asyncpg
from Typing import *
import asyncio


parser = argparse.ArgumentParser()
parser.add_argument('--nodes', nargs='+', required=True, help='Nodes to load-balance across. Example: --nodes http://localhost:8545 http://localhost:8546 \nMust be at least one.')
parser.add_argument('--port', type=int, default=8000, help='Port to run the load-balancer on.')
parser.add_argument('--connection', type=str, required=True, help='A PostgreSQL DSN for executionbackup to connect to for client call reporting.')
args = parser.parse_args()


app = Sanic('router')
logger.setLevel(logging.ERROR) # we don't want to see the sanic logs

class coloredFormatter(logging.Formatter):

    reset =  "\x1b[0m"

    FORMATS = {
        logging.DEBUG: '[%(asctime)s] %(levelname)s - %(message)s' + reset,
        logging.INFO: f'[%(asctime)s] {Colors.GREEN}%(levelname)s{reset} - %(message)s',
        logging.WARNING: f'[%(asctime)s] {Colors.YELLOW}%(levelname)s{reset} - %(message)s',
        logging.ERROR: f'[%(asctime)s] {Colors.RED}%(levelname)s{reset} - %(message)s',
        logging.CRITICAL: f'[%(asctime)s] {Colors.RED}%(levelname)s{reset} - %(message)s'
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)

logger = logging.getLogger('router')
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
ch.setFormatter(coloredFormatter())
logger.addHandler(ch)


Account = executionbackup.Account
    
router = executionbackup.NodeRouter(['http://192.168.86.37:2000'])
accounts: Dict[str, Account] = {}

# make db table: CREATE TABLE accounts ("key" TEXT UNIQUE, "callamount" BIGINT, "calljson" TEXT)

async def setAccounts():
    async with router.db.acquire() as con:
        async with con.transaction():
            async for record in con.cursor("""SELECT * FROM accounts;"""):
                accounts[record['key']] = Account(record['key'], record['callamount'], ujson.loads(record['calljson']))   

async def doDump():
    for k, v in accounts.items():
        await router.db.execute("""INSERT INTO accounts (key, callamount, calljson) VALUES ($1, $2, $3) ON CONFLICT (key) DO UPDATE SET callamount=$2, calljson=$3;""", k, v.callAmount, ujson.dumps(v.callDict))

async def dumpIntoDb():
    await asyncio.sleep(900) # since it's called at the start of the execution there are still no calls
    while True:
        await doDump()
        asyncio.sleep(900) # 15m

@app.before_server_start
async def before_start(app: Sanic, loop):
    await router.setup()
    app.add_task(router.repeat_check())
    router.db = None
    try:
        router.db = await asyncpg.create_pool('postgresql://tennisbowling:wergh@192.168.86.37/tennisbowling')
    except Exception as e:
        logger.critical(f'Could not connect to postgres database: {e}')
    await setAccounts()
    app.add_task(dumpIntoDb())

@app.before_server_stop
async def after_stop(app: Sanic, loop):
    await router.stop() # no more requests come
    await doDump()
    await router.db.close()
    
@app.route('/<path:path>', methods=['POST'])
async def route(request: Request, path: str):
    auth = (request.raw_url.decode()).strip('/')
    
    accnt = accounts.get(auth)
    if not accnt:
        return response.json({'error': 'api key not authorized'}, status=403)

    try:
        if request.json['method'].startswith('engine_'):
            return response.json({'error': 'method not allowed'}, status=403)
    except KeyError:
        return response.json({'error': 'method is required'}, status=404)

    await router.route(request, None, None)
    try:
        call = request.json['method']
    except KeyError: return
    if not accnt.callDict.get(call):
        accnt.callDict[call] = 1
    else:
        accnt.callDict[call] += 1
    accnt.callAmount += 1

@app.route('/executionbackup/version', methods=['GET'])
async def ver(request: Request):
    return response.text(f'executionbackup-{executionbackup.__version__}/{system() + release()}-{machine()}/python{python_version()}')

@app.route('/executionbackup/status', methods=['GET'])
async def status(request: Request):
    #await router.recheck()
    ok = 200 if router.alive_count > 0 else 503
    return response.json({'status': ok, 'alive': router.alive_count, 'dead': router.dead_count, 'clients': len(accounts)}, status=ok)

@app.route('/executionbackup/addkey', methods=['POST'])
async def addkey(request: Request):
    key = request.json['key']

    if accounts.get(key):
        return response.json({'success': False, 'message': 'key already exsts'})        # TODO: add error codes
    await router.db.execute("""INSERT INTO accounts VALUES ($1, $2, $3)""", key, 0, '{}')
    accounts[key] = Account(key)
    return response.json({'success': True})

@app.route('/executionbackup/removekey', methods=['POST'])
async def removekey(request: Request):
    if not request.json.get('Auth') == 'I love tennis':
        return response.json({'success': False, 'message': 'auth failed'}, status=403)
    key = request.json['key']

    if not accounts.get(key):
        return response.json({'success': False, 'message': 'key does not exist'})
    await router.db.execute("""DELETE FROM accounts WHERE "key" = $1;""", key)
    del accounts[key]
    return response.json({'success': True})

@app.route('/executionbackup/stats', methods=['GET'])
async def stats(request: Request):
    if not request.json.get('Auth') == 'I love tennis':
        return response.json({'success': False, 'message': 'auth failed'}, status=403)
    key = request.json['key']

    if not accounts.get(key):
        return response.json({'success': False})
    
    return response.json({'success': True, 'stats': str(accounts[key].callDict)})

@router.listener('node_offline')
async def node_offline(url: str):
    print(f'Node {url} is offline')

@router.listener('all_nodes_offline')
async def all_nodes_offline():
    print('All nodes are offline!')

@router.listener('node_online')
async def node_online(url: str):
    print(f'Node {url} is online')

@router.listener('node_router_online')
async def node_router_online():
    print('Node router online')

app.run('0.0.0.0', port=8001, access_log=False)
