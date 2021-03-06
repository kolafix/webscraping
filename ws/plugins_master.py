from .plugins import *
import time
import pickle
import os
import logging
import ws.bad as bad
import urllib.error
import http.client
from .tools import misc
import multiprocessing
import datetime


def generate_forecast_filepath(pname, city, basepath=''):
    """Generate forecast filepath.

    basepath/city/pname
    """
    posix_time = time.time()
    utc_posix_time = posix_time + time.timezone

    forecast_dir = os.path.join(basepath, city, pname)
    # exist_ok=True to make the function thread safe.
    os.makedirs(forecast_dir, exist_ok=True)

    filename = str(utc_posix_time).replace('.', 's', 1) + '.forecast'
    forecast_path = os.path.join(forecast_dir, filename)

    return forecast_path


def get_citylist():
    """Return list with all city names."""
    # XXX should we use another format than pickle?
    fp = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'citylist.dump')
    citylist = pickle.load(open(fp, 'rb'))
    citylist = [str(i) for i in citylist]

    return citylist


def store_forecast(city, pname, basepath=''):
    """Store forecast for city from plugin pname."""
    logging.debug('args city=%s pname=%s basepath=%s', city, pname,
                 basepath)

    forecast_data = None
    p = load_plugin(str(pname))

    try:
        url = p.build_url(str(city))
    except bad.City:
        logging.error('plugin %s cannot deal with city %s', pname, city)
        return -1

    failcounter = 0
    continue_loop = True
    while continue_loop:
        try:
            forecast_data = misc.download_from_url(url)
            continue_loop = False
            if failcounter == 0:
                logging.info('Queried %s for %s successfully', pname, city)
        except urllib.error.HTTPError as err:
            failcounter += 1
            logging.error("%s for url %s", err, url)
            logging.info("Trying again...")
            logging.info("This was attempt number " +str(failcounter))
        except http.client.IncompleteRead as err:
            logging.error("%s", err)

        if failcounter > 0 and continue_loop == False:
            logging.info("SUCCESS! This time querying %s worked", pname)

        if continue_loop == False:
            break

    filepath = generate_forecast_filepath(pname, city, basepath)
    misc.save_to_disk(forecast_data, filepath)

    return forecast_data


def store_forecasts_loop(cities, pname, basepath=''):
    try:
        for city in list(cities):
            store_forecast(city, pname, basepath)
    except KeyboardInterrupt as err:
        raise KeyboardInterrupt(err)


def store_forecasts(cities, pnames, basepath=''):
    """store_forecast but takes list of cities and plugin names.

    Each plugin gets its own process. This way a plugin can rate limit without
    blocking the others.
    """
    for pname in list(pnames):
        p = multiprocessing.Process(target=store_forecasts_loop,
                                    args=(cities, pname, basepath))
        p.start()


def forecasts_newer_than(newer_than, basepath=''):
    forecast_lists = {}
    for city in os.listdir(basepath):
        for provider in os.listdir(os.path.join(basepath, city)):
            if provider not in forecast_lists:
                forecast_lists[provider] = []
            for forecast in os.listdir(os.path.join(basepath, city, provider)):
                utc_posix_time = float(forecast.replace('s', '.',
                                                        1)[:-len('.forecast')])
                if utc_posix_time > newer_than:
                    filepath = os.path.join(basepath, city, provider, forecast)
                    with open(filepath, 'r') as fd:
                        forecast_lists[provider].append([fd.read(), city,
                                                         datetime.datetime.fromtimestamp(utc_posix_time)])

    return forecast_lists


def pandize_plugin_forecasts(forecast_lists, pname, database_filepath):
    p = load_plugin(str(pname))
    for forecast_list in forecast_lists:
        logging.debug('pname %s city %s date %s', pname, forecast_list[1],
                      forecast_list[2])
        pandas_table = p.pandize(*forecast_list)
        # XXX: maltimore works on this function
        #insert_into_master_frame(pandas_table, database_filepath)


def pandize_forecasts(pnames, database_filepath='', basepath='', newer_than=0):
    forecast_lists = forecasts_newer_than(newer_than, basepath)
    for pname in list(pnames):
        pandize_plugin_forecasts(forecast_lists[pname], pname,
                                 database_filepath)
