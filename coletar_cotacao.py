# -*- coding: utf-8 -*-
"""
Coleta diária de preços do café (saca de 60 kg) em várias fontes e
acrescenta uma linha ao arquivo precos_cafe.csv.

Versão em script do notebook "Coleta de Preços do Café" (Aryane Cassimiro Machado),
adaptada para rodar sem o Google Colab (ex.: GitHub Actions).
"""
import os
import random
import re
import sys
from datetime import datetime, timedelta
from enum import Enum

import pandas as pd
import pytz
import requests
from bs4 import BeautifulSoup

CSV_PATH = os.environ.get("CSV_PATH", "precos_cafe.csv")
TIMEOUT = 30  # segundos por requisição
DIGITS_FOR_FLOATS = 2

AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/116.0",
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.6 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36 Edg/115.0.1901.188",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.0.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36",
]


class Sources(str, Enum):
    B3 = "b3"
    CEPEA = "cepea"
    COOPAMA = "coopama"
    COOPERCAM = "coopercam"
    CCMG = "ccmg"
    COOXUPE = "cooxupe"
    CAFEPOCOS = "cafe-pocos"
    COCAPEC = "cocapec"
    AIBA = "aiba"
    CCCV = "cccv"


# ---------------------------------------------------------------- utilidades
def get_agent():
    return random.choice(AGENTS)


def today_br():
    return datetime.now(pytz.timezone("America/Sao_Paulo")).strftime("%d/%m/%Y")


def retain_numbers_in_string(str_value):
    return "".join(c for c in str_value if c in ",0123456789")


def comma_to_point(str_value):
    return str_value.replace(",", ".")


def brl_to_float(str_value):
    # "R$ 1.704,00" -> "1704,00" -> "1704.00" -> 1704.0
    return float(comma_to_point(retain_numbers_in_string(str_value)))


def fetch(url, headers):
    response = requests.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response


# ---------------------------------------------------------------- coletores
def price_b3_via_coox(headers, url):
    def parse_numeric_value(raw_val):
        cleaned = "".join(c for c in raw_val if c.isdigit() or c in ".,-")
        if "," in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        return float(cleaned)

    us_price = 0
    dollar_price = 0
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    for row in soup.find_all("tr"):
        columns = row.find_all(["td", "th"])
        if len(columns) > 1:
            desc = columns[0].text.strip()
            if "DOL COM" in desc:
                dollar_price = round(parse_numeric_value(columns[1].text.strip()), 4)
            if "ICF" in desc:
                us_price = round(parse_numeric_value(columns[1].text.strip()), DIGITS_FOR_FLOATS)
    print(f"Dólar Comercial: {dollar_price}, ICF: {us_price}")
    return round(us_price * dollar_price, DIGITS_FOR_FLOATS)


def price_cepea(headers, url):
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    table = soup.find("table", {"id": "imagenet-indicador1"})
    tds = table.find_all("td")
    price = float(comma_to_point(retain_numbers_in_string(tds[1].text.strip())))
    return round(price, DIGITS_FOR_FLOATS)


def price_coopama(headers, url):
    price = 0
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    found = False
    for span in soup.find_all("span", {"class": "col"}):
        if found:
            price = float(retain_numbers_in_string(span.text)[:4])  # 1º valor da faixa
            break
        if "Duro tipo 6" in span.text:
            found = True
    return round(price, DIGITS_FOR_FLOATS)


def price_coopercam(headers, url):
    price = 0
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    for link in soup.find_all("a"):
        if link.text.strip().startswith("Duro Limpo"):
            price = brl_to_float(link.find("b").text)
            break
    return round(price, DIGITS_FOR_FLOATS)


def price_ccmg(headers, url):
    # Desativada por padrão: o site bloqueia acessos automatizados (HTTP 403).
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        if re.search(r"/cotacao-do-cafe/\d{2}-\d{2}-\d{4}/?$", a["href"]) and a["href"] not in links:
            links.append(a["href"])
    if not links:
        today = datetime.now(pytz.timezone("America/Sao_Paulo"))
        links = [url + (today - timedelta(days=i)).strftime("%d-%m-%Y") + "/" for i in range(10)]
    for link in links:
        site = requests.get(link, headers=headers, timeout=TIMEOUT)
        if site.status_code != 200:
            continue
        for row in BeautifulSoup(site.content, "html.parser").find_all("tr"):
            columns = row.find_all("td")
            if len(columns) > 1 and "tipo 6, bebida dura" in columns[0].text:
                return round(brl_to_float(columns[1].text), DIGITS_FOR_FLOATS)
    return 0


def price_cooxupe(headers, url):
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    label = soup.find(string=lambda s: s and "Café fino Cooxupé" in s)
    return round(brl_to_float(label.find_next("strong").text), DIGITS_FOR_FLOATS)


def price_cafe_pocos(headers, url):
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    tables = soup.find_all("table", class_="cot-fisicas")
    dates = soup.find_all(class_="fechamento")
    for index, table in enumerate(tables):
        for row in table.find_all("tr"):
            columns = row.find_all("td")
            if len(columns) > 1 and "Poços de Caldas" in columns[0].text:
                value = columns[1].text.strip()
                if any(c.isdigit() for c in value):  # ignora "s/ cotação"
                    if index < len(dates):
                        print("Café Poços -", dates[index].text.strip())
                    return round(brl_to_float(value), DIGITS_FOR_FLOATS)
    return 0


def price_cocapec(headers, url):
    price = 0
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    for item in soup.find_all("article", class_="quotes-item"):
        title = item.find("h3")
        if title and "Café 6 Duro" in title.text:
            price = brl_to_float(item.find("div", class_="quotes-item__value").text)
            break
    return round(price, DIGITS_FOR_FLOATS)


def price_aiba(headers, url):
    price = 0
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    for item in soup.find_all("div", class_="ticker-item"):
        name = item.find("span", class_="t-name")
        if name and name.text.strip() == "Café":
            price = brl_to_float(item.find("span", class_="t-price").text)
            break
    return round(price, DIGITS_FOR_FLOATS)


def price_cccv(headers, url):
    soup = BeautifulSoup(fetch(url, headers).content, "html.parser")
    block = soup.find("div", class_="cotacao-conilon")
    row = block.find("ul", class_="bottom-conilon")
    return round(brl_to_float(row.find_all("li")[-1].text), DIGITS_FOR_FLOATS)


COLLECTORS = {
    #  Fonte              Função               URL                                                                                          Ativa?
    Sources.B3:        (price_b3_via_coox, "https://hubdocafe.cooxupe.com.br",                                                          True),
    Sources.CEPEA:     (price_cepea,       "https://www.cepea.org.br/br/indicador/cafe.aspx",                                           True),
    Sources.COOPAMA:   (price_coopama,     "https://www.coopama.com.br/",                                                               True),
    Sources.COOPERCAM: (price_coopercam,   "https://coopercam.com.br/cotacoes",                                                         True),
    Sources.CCMG:      (price_ccmg,        "https://cccmg.com.br/cotacao-do-cafe/",                                                     False),  # HTTP 403
    Sources.COOXUPE:   (price_cooxupe,     "https://hubdocafe.cooxupe.com.br",                                                          True),
    Sources.CAFEPOCOS: (price_cafe_pocos,  "https://www.noticiasagricolas.com.br/cotacoes/cafe/cafe-arabica-mercado-fisico-tipo-6-duro", True),
    Sources.COCAPEC:   (price_cocapec,     "https://www.cocapec.com.br/",                                                               True),
    Sources.AIBA:      (price_aiba,        "https://aiba.org.br/",                                                                      True),
    Sources.CCCV:      (price_cccv,        "https://www.cccv.org.br/",                                                                  True),
}


# ---------------------------------------------------------------- coleta e CSV
def collect_prices():
    headers = {"User-Agent": get_agent()}
    prices = {"data": [today_br()]}
    for source, (collect, url, active) in COLLECTORS.items():
        if not active:
            continue
        try:
            value = collect(headers, url)
        except Exception as error:  # uma fonte com problema não derruba as outras
            print(f"[ERRO] {source.value}: {error!r}")
            value = 0
        prices[source.value] = [value if value and value > 0 else None]  # falha -> vazio
        print(f"{source.value:>11}: {value}")
    return prices


def save_csv(prices, path=CSV_PATH):
    """Acrescenta a linha do dia. Se o dia já existir, substitui (sem duplicar)."""
    df_new = pd.DataFrame(prices)
    if os.path.exists(path):
        df_existing = pd.read_csv(path)
        df_existing = df_existing[df_existing["data"] != prices["data"][0]]
        df_final = pd.concat([df_existing, df_new], ignore_index=True)
    else:
        df_final = df_new
    df_final.to_csv(path, index=False)
    return df_final


def main():
    prices = collect_prices()
    collected = [v[0] for k, v in prices.items() if k != "data" and v[0] is not None]
    if not collected:
        print("Nenhuma fonte retornou preço. CSV não foi alterado.")
        sys.exit(1)
    df = save_csv(prices)
    print(f"CSV atualizado: {CSV_PATH} ({len(df)} linhas)")


if __name__ == "__main__":
    main()
