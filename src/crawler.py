"""Crawl player stats from pleagueofficial.com."""
import asyncio
import json
import os

import httpx
from bs4 import BeautifulSoup


class ElementNotFoundError(Exception):
    """Exception raised when a specific HTML element cannot be found."""

    def __init__(self, element_description):
        """
        Exception raised when a specific HTML element cannot be found.

        Args:
            element_description (str): A description of the missing HTML
            element.

        Attributes:
            element_description (str): A description of the missing HTML
            element.
        """
        super().__init__(
            f"Element not found: {element_description}."
            "Please check the page structure of the URL."
        )


class MissingAttributeError(Exception):
    """Exception for missing HTML element attribute."""

    def __init__(self, element_name, attr_name):
        """
        Exception for missing HTML element attribute.

        Args:
            element_name (str): The name of the HTML element.
            attr_name (str): The name of the missing attribute.

        Attributes:
            element_name (str): The name of the HTML element.
            attr_name (str): The name of the missing attribute.
        """
        super().__init__(
            f"Element '{element_name}' is missing the '{attr_name}' attribute."
        )


def _abs_path(filename: str):
    source_dictionary = os.path.dirname(__file__)
    return os.path.join(source_dictionary, filename)


URL = "https://pleagueofficial.com/stat-player"
FILE_ENCODING = "utf-8"
CONFIG_FILENAME = _abs_path("url.json")
DATA_FILENAME = _abs_path("output.json")
PARSER = "lxml"
PER_MODE = {"累計數據": "data-total", "平均數據": "data-avg"}
STATS_NAME = {
    # "球員": "PLAYER_NAME",
    "背號": "JERSEY_NUMBER",
    "球隊": "TEAM",
    "出賽次數": "GP",
    "時間 (分)": "MIN",
    "兩分命中": "FGM2PT",
    "兩分出手": "FGA2PT",
    "兩分%": "2PT_PCT",
    "三分命中": "FGM3PT",
    "三分出手": "FGA3PT",
    "三分%": "3PT_PCT",
    "罰球命中": "FTM",
    "罰球出手": "FTA",
    "罰球%": "FT_PCT",
    "得分": "PTS",
    "攻板": "OREB",
    "防板": "DREB",
    "籃板": "REB",
    "助攻": "AST",
    "抄截": "STL",
    "阻攻": "BLK",
    "失誤": "TOV",
    "犯規": "PF",
}


async def get_soup(
    client: httpx.AsyncClient, url: str, retries: int = 2
) -> BeautifulSoup:
    """
    Send an HTTP GET request and parse the response as BeautifulSoup.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.
        url (str): The URL to send the GET request to.
        retries (int): The number of retries for failed requests.

    Returns:
        BeautifulSoup: A BeautifulSoup object containing parsed HTML
        content.
    """
    try:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        if retries > 0:
            retries -= 1
            await get_soup(client, url, retries)
        print(
            f"{url} reached maximum retry attempts, "
            f"unable to complete request."
        )
        raise exc
    except httpx.HTTPStatusError as exc:
        print(
            f"Request to {url} received an HTTP response status code: "
            f"{exc.response.status_code}"
        )
        raise exc
    except httpx.RequestError as exc:
        print(f"Error occurred while making a request to {url}")
        raise exc
    return BeautifulSoup(response.text, PARSER)


async def get_season(
    client: httpx.AsyncClient, season: str, retries: int = 2
) -> tuple[BeautifulSoup, str]:
    """
    Wrapper for get_soup() and provides an additional return value.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.
        season (str): The season associated with the url.
        retries (int, optional): The number of retries for failed
        requests.
        Default is 2.

    Returns:
        tuple: A tuple containing a BeautifulSoup object and the
        associated season.
    """
    return await get_soup(client, f"{URL}/{season}", retries), season


async def load_config_from_web(client: httpx.AsyncClient) -> dict:
    """
    Send GET request and parse as configuration.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.

    Returns:
        dict: A dictionary containing season data, season types, and
        URLs.
    """
    soup = await get_soup(client, URL)
    season_name_element = soup.find(id="season_name")
    if season_name_element is None:
        raise ElementNotFoundError("id='season_name'")
    options = (option for option in season_name_element.find_all("option"))
    seasons = [option.text for option in options]
    if len(seasons) == 0:
        raise ElementNotFoundError("option")
    tasks = [asyncio.create_task(get_season(client, s)) for s in seasons]
    config = {}
    while tasks:
        done, tasks = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            soup, season = await task
            stage_name_element = soup.find(id="stage_sn")
            if stage_name_element is None:
                raise ElementNotFoundError("id='stage_sn'")
            options = stage_name_element.find_all("option")
            if len(options) == 0:
                raise ElementNotFoundError("option")
            season_config = config[season] = {}
            for option in options:
                season_type = option.text
                if "value" not in option.attrs:
                    raise MissingAttributeError("option", "value")
                season_type_value = option["value"]
                season_config[
                    season_type
                ] = f"{URL}/{season}/{season_type_value}#record"
    return config


def is_valid_config(config: dict) -> None:
    """
    Check if the configuration is valid.

    Args:
        config (dict): The configuration dictionary to validate.

    Raises:
        ValueError: If the configuration is invalid.

    Notes:
        This function checks the following conditions:
        - The configuration must be a dictionary.
        - Each season in the configuration must have its own dictionary.
        - Season values must be in the format "YYYY-YY" where the second
        season is one greater than the first.
        - The season types within each season must be one of: "例行賽",
        "季後賽", "總冠軍賽".

        This function does not check if URLs are reachable to avoid
        potentially lengthy operations.
    """
    default_season_type = {"例行賽", "季後賽", "總冠軍賽"}
    if not isinstance(config, dict):
        raise ValueError("Input 'config' must be a dictionary.")
    for season in config:
        if not isinstance(config[season], dict):
            raise ValueError(
                f"config['{season}'] must be a dictionary containing season "
                "data, not {type(config[season])}."
            )
        # If it can't convert to integer, it will raise ValueError.
        first_year, second_year = map(int, season.split("-", 1))
        if first_year % 100 + 1 != second_year:
            raise ValueError
        for season_type in config[season]:
            if season_type not in default_season_type:
                raise ValueError


def load_from_file(filename: str, chunk_size: int = 1024) -> str:
    """
    Load data from a file and convert it into a string.

    Args:
        filename (str): The name of the file to read.
        chunk_size (int, optional): The size of each data chunk to read
        from the file. Default is 1024.

    Returns:
        str: The contents of the file as a string.
    """
    with open(filename, "r", encoding=FILE_ENCODING) as file:
        buffer = []
        while True:
            chunk = file.read(chunk_size)
            if not chunk:
                break
            buffer.append(chunk)
    return "".join(buffer)


async def load_config(client: httpx.AsyncClient) -> dict:
    """
    Load configuration data from a file or web.

    If the file does not exist or its format is invalid,fetch the data
    from the web and save it to the file.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.

    Returns:
        dict: A dictionary containing season data, season types, and
        URLs.
    """
    try:
        config = json.loads(load_from_file(CONFIG_FILENAME))
        is_valid_config(config)
        return config
    except FileNotFoundError:
        print(f"找不到 {CONFIG_FILENAME}. 從 Pleague 下載.")
    except (json.JSONDecodeError, ValueError):
        pass
    config = await load_config_from_web(client)
    with open(CONFIG_FILENAME, "w", encoding=FILE_ENCODING) as json_file:
        json.dump(config, json_file, ensure_ascii=False, indent=2)
    return config


async def parse_webpage(
    client: httpx.AsyncClient, url: str, season: str, season_type: str
):
    """
    Parse data from a web page and return it as a dictionary.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.
        url (str): The URL of the web page to parse.
        season (str): The season associated with the data.
        season_type (str): The type of season data.

    Returns:
        dict: A dictionary containing parsed data for players and their
        statistics.
        str: The associated season.
        str: The season type.
    """
    database = {}
    soup = await get_soup(client, url)
    tbody = soup.find("tbody")
    for data_type_name, data_type in PER_MODE.items():
        for row in tbody.find_all("tr"):
            columns = row.find_all("td")
            player_name = row.th.a.text.strip()
            player_data = [col[data_type] for col in columns]

            stat = {name: stat for name, stat in zip(STATS_NAME, player_data)}
            if player_name not in database:
                database[player_name] = {}
            database[player_name][data_type_name] = stat
    return database, season, season_type


async def load_data(client):
    """
    Parse data from web or file and return it as a dictionary.

    Args:
        client (httpx.AsyncClient): An asynchronous HTTP client.
        url (str): The URL of the web page to parse.
        season (str): The season associated with the data.
        season_type (str): The type of season data.

    Returns:
        dict: A dictionary containing parsed data for players and their
        statistics.
        str: The associated season.
        str: The season type.
    """
    try:
        return json.loads(load_from_file(DATA_FILENAME))
    except FileNotFoundError:
        print(f"找不到 {DATA_FILENAME}. 從 Pleague 下載.")
    except (json.JSONDecodeError, ValueError):
        pass
    config = await load_config(client)
    database = {}
    tasks = []
    for season in config:
        database[season] = {}
        for season_type in config[season]:
            tasks.append(
                asyncio.create_task(
                    parse_webpage(
                        client,
                        config[season][season_type],
                        season,
                        season_type,
                    ),
                )
            )
    while tasks:
        done, tasks = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_COMPLETED
        )

        for task in done:
            data, season, season_type = await task
            database[season][season_type] = data
    with open(DATA_FILENAME, "wt", encoding=FILE_ENCODING) as json_file:
        json_file.write(json.dumps(database, ensure_ascii=False, indent=2))
    return database


async def main():
    """Main function of crawler."""
    with httpx.AsyncClient() as client:
        database = await load_data(client)
    return database


if __name__ == "__main__":
    asyncio.run(main())
