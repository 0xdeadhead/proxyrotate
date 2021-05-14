import asyncio
import sys
import os
from proxyrotate import proxyvalidate
from time import sleep
from argparse import ArgumentParser
from termcolor import colored
from tqdm import tqdm
from art import text2art


# _delay in secs b/w validating next set of proxies,_timeout for proxy validation
async def updateProxies(_proxies, _bar, _configDir, _delay=20, _timeout=15, _concurrency=120, _retries=2):
    server_id = 0
    # set PROXY_STATE Variable for set kill_flag(-sf flag) for haproxy
    PROXY_STATE = "INACTIVE"
    while True:
        _newProxies = await proxyvalidate.getProxyList(
            bar=_bar, _existingProxies=_proxies, _timeout=_timeout, _concurrency=_concurrency, _retries=_retries)
        # Reading newly validated proxies
        _proxy = _newProxies.dequeue()
        _newCount = 0
        # reading old proxies
        with open(f"{_configDir}/proxies.cfg") as config_file:
            _lines = config_file.readlines()
        # Inserting newly validated proxies to config_file
        with open(f"{_configDir}/proxies.cfg", "w") as config_file:
            newProxieString = ""
            while _proxy:
                if _proxies.enqueue(_proxy):
                    newProxieString += f"    server s{server_id} {_proxy['ip']}:{_proxy['port']}\n"
                    server_id += 1
                    _newCount += 1
                _proxy = _newProxies.dequeue()
            # Inserting new proxies at top for round robin support
            _lines.insert(16, newProxieString)
            config_file.write("".join(_lines))
        if PROXY_STATE == "INACTIVE":
            kill_flag = ""
            PROXY_STATE = "ACTIVE"
        else:
            kill_flag = f"-sf $(cat {_configDir}/haproxy.pid)"
        # restarting proxy
        p = await asyncio.create_subprocess_shell(f"haproxy -D -f {_configDir}/proxies.cfg -p {_configDir}/haproxy.pid {kill_flag}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await p.communicate()
        if err:
            _bar.write(colored(f"{err.decode()}", color="red"))
        elif out:
            _bar.write(colored(f"{out.decode()}", color="cyan"))
        _bar.write(
            colored(f"[*] Restarted haproxy with {_newCount} new proxies written to {_configDir}/proxies.cfg", color="cyan"))
        sleep(_delay)


def main():
    parser = ArgumentParser()
    print(text2art("proxyrotate", font="doubleshorts"), file=sys.stderr)
    parser.add_argument(
        "-d", "--delay", help="Cooldown b/w validating next set of proxies", default=20, type=int)
    parser.add_argument("-t", "--timeout",
                        help="Timeout for each proxy", default=15, type=int)
    parser.add_argument("-c", "--concurrency",
                        help="No of concurrent proxy validations", default=120, type=int)
    parser.add_argument(
        "-r", "--retries", help="No of retries before invalidating a proxy", default=2, type=int)
    parser.add_argument("-A", "--alg", choices=['roundrobin', 'leastconn'],
                        default="roundrobin", help="Load balancing algorithm")
    parser.add_argument("-P", "--port", default=4444,
                        help="port for binding haproxy frontend", type=int)
    args = parser.parse_args()

    DELAY, TIMEOUT, CONCURRENCY, RETRIES, ALG, PORT = args.delay, args.timeout, args.concurrency, args.retries, args.alg, args.port

    # Initial Configuration
    initial_doc = f'''global
    daemon
    maxconn 256

    defaults
    mode tcp
    timeout connect 5000ms
    timeout client 50000ms
    timeout server 50000ms

    frontend rotatingproxies
    bind 127.0.0.1:{PORT}
    default_backend proxy_servers

    backend proxy_servers
    balance {ALG}
'''

    try:
        _configDir = '/tmp/proxyrotate'
        os.system(f"mkdir -p {_configDir}")
        # Initializing configuration file
        with open(f"{_configDir}/proxies.cfg", "w") as config_file:
            config_file.write(initial_doc)
        with tqdm(desc=f"haproxy configuration: proxy_addr={colored('http://127.0.0.1:'+str(PORT),'white',attrs=['bold'])} algorithm={colored(ALG,'white',attrs=['bold'])}          Validating proxies", total=200, unit="req") as bar:
            _proxies = proxyvalidate.CircularQueue()
            asyncio.run(updateProxies(_proxies, bar, _configDir, _delay=DELAY,
                        _timeout=TIMEOUT, _concurrency=CONCURRENCY, _retries=RETRIES))
    except Exception as e:
        print(colored(f"Exiting Reason {e}"))
    except KeyboardInterrupt:
        print(colored(f"Exiting"))
    finally:
        os.system(f"rm -r {_configDir} ; killall -9 haproxy")


if __name__ == "__main__":
    main()
