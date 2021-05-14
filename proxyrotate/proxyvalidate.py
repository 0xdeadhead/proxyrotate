import asyncio
import aiohttp
import sys
import re
from termcolor import colored
from tqdm import tqdm
from bs4 import BeautifulSoup

# Queue for storing proxies


class CircularQueue():
    def __init__(self):
        self.queue = []

    def enqueue(self, data):
        if not data in self.queue:
            self.queue.append(data)
            return True
        else:
            return False

    def dequeue(self):
        if len(self.queue) == 0:
            return None
        else:
            return self.queue.pop(0)

    def display(self):
        for element in self.queue:
            print(element, file=sys.stderr)

    def size(self):
        return len(self.queue)


# Extract proxies from sources


async def extractProxies(_url, _client, _proxies, _bar):
    # _bar.write(colored(f"[*] Fetching proxy list from {_url}", color="cyan"))
    async with _client.get(_url) as resp:
        _pageSource = await resp.text()
        if _url == "https://sslproxies.org/" or _url == "https://free-proxy-list.net/":
            soup = BeautifulSoup(_pageSource, 'html.parser')
            proxies_table = soup.find(id='proxylisttable')
            for row in proxies_table.tbody.find_all('tr'):
                _proxies.enqueue({
                    'ip':   row.find_all('td')[0].string,
                    'port': row.find_all('td')[1].string
                })


# Filtering Non-functional proxies


async def filterProxies(_client, _proxies, _proxy, _rx4, _rx6, _sem, _retries, _pbar, _originIp=None):
    while _retries != 0:
        try:
            await _sem.acquire()
            async with _client.get("https://httpbin.org/ip", proxy=f"http://{_proxy['ip']}:{_proxy['port']}") as resp:
                respjson = await resp.json()
                respData = respjson["origin"]
                _pbar.update()
                _sem.release()
                # Check if proxy discloses origin IP and skip adding the proxies
                if _originIp in respData:
                    _pbar.write(
                        f"Transparent : {_proxy['ip']}:{_proxy['port']}", file=sys.stderr)
                    break
                # Check if Ip address is present in resp
                if _rx4.search(respData) or _rx6.search(respData):
                    _proxies.enqueue(_proxy)
                    break
        # Handling Timeout and other exceptions
        except Exception:
            _pbar.update()
            _sem.release()
        _retries -= 1

# _existingProxies is used for only querying proxies which doesnt exist in current proxylist see line 92


async def getProxyList(_timeout=15, _concurrency=120, _retries=2, bar=None, _existingProxies=CircularQueue()):
    clientTimeout = aiohttp.ClientTimeout(total=_timeout)
    # Set progress bar if it doesnt exists
    if not bar:
        bar = tqdm(desc="Validating Proxies", total=_retries*100, unit="req")
    async with aiohttp.ClientSession(timeout=clientTimeout) as client:
       # Fetching list of proxies from sources and extracting
        sources = ["https://free-proxy-list.net/", "https://sslproxies.org/"]
        proxies = CircularQueue()
        proxyTasks = [extractProxies(url, client, proxies, bar)
                      for url in sources]
        await asyncio.gather(*proxyTasks)
        # Querying for Origin Ip for removing transparent proxies
        async with client.get("https://httpbin.org/ip") as resp:
            respjson = await resp.json()
            originIP = respjson["origin"]
        no_of_reqs = proxies.size()*_retries
        sem = asyncio.Semaphore(_concurrency)
        # Regexes for IP adresses
        rx4 = re.compile(r"^^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")
        rx6 = re.compile(r"(([0-9a-fA-F]{1,4}:){7,7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(:[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]{1,}|::(ffff(:0{1,4}){0,1}:){0,1}((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])|([0-9a-fA-F]{1,4}:){1,4}:((25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9])\.){3,3}(25[0-5]|(2[0-4]|1{0,1}[0-9]){0,1}[0-9]))")
        tasks = []
        proxy = proxies.dequeue()
        # Creating Async Tasks for Ip verification
        # reset total elements in bar
        bar.total = 0
        while proxy:
            # check for existince of current proxy in valid proxies
            if not proxy in _existingProxies.queue:
                # update total items in progressbar i.e .. add no of retries to current
                bar.total += _retries
                tasks.append(filterProxies(client, proxies,
                                           proxy, rx4, rx6, sem, _retries, bar, _originIp=originIP))
            proxy = proxies.dequeue()
        await asyncio.gather(*tasks)
        # resetting Progressbar
        bar.update(-bar.n)
        return proxies


if __name__ == "__main__":
    proxy_q = asyncio.run(getProxyList(_timeout=20))
    print(proxy_q.size())
