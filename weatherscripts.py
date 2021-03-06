import pandas as pd
import numpy as np
import sys
import os
import sqlite3
import smtplib
from urllib.request import Request, urlopen
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import ssl
import bs4 as bs
import time
import logging
import pytz
from shutil import copy2
from sqlalchemy import create_engine
import datetime
import urllib
import traceback
from multiprocessing import Process
import multiprocessing as mp
from selenium import webdriver
import urllib.request
from selenium.webdriver.firefox.options import Options as firefox_options
from selenium.webdriver.chrome.options import Options as chrome_options
# credentials for Azure SQL
def get_credentials():
    # credentials for Azure SQL
    path_to_file = "C:/Users/J_Ragbeer/PycharmProjects/weatherdata/"
    with open(path_to_file + "server_credentials.txt", 'r') as file:
        temp = file.read().splitlines()
        return list(temp)
def azure_sql_connection():

    # Azure SQL
    credentials = get_credentials()
    dbschema = 'dbo,schema,public,online'  # Searches left-to-right
    connection_string = "Driver={ODBC Driver 17 for SQL Server};" + "Server={};Database={};Uid={};Pwd={};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryPassword".format(
        credentials[0], credentials[1], credentials[2], credentials[3])
    engine = create_engine("mssql+pyodbc:///?odbc_connect={}".format(urllib.parse.quote_plus(connection_string)),
                           connect_args={'options': '-csearch_path={}'.format(dbschema)})
    return engine

# augment a dataframe of weather data
def hmdxx(temp, dew_temp):
    """

    returns the humidex reading given the air temp and dew temp

    :param x: air temp in Celsius
    :param y: dewpoint in Celsius
    :return: humidex reading as a float
    """
    return temp + (0.5555 * (6.11 * np.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_temp)))) - 10))
def clean_weather(weather):

    """
    cleans a raw weather dataframe....
    Adds cyclical variables such as weekday, hour, month and formats some, to remove degree symbol, drops columns

    :param weather: dataframe with weather data
    :return: the same dataframe as input, but with more useful columns
    """
    weather.index = pd.to_datetime(weather.index)
    weather.fillna(method='ffill', inplace=True)
    weather['Humidex'] = pd.Series([hmdxx(x[5], x[7]) for x in weather.itertuples()], index=weather.index)
    weather['Hour'] = pd.Series([int(x[0].hour) for x in weather.itertuples()], index=weather.index)
    weather['Weekday'] = pd.Series([int(x[0].weekday()) for x in weather.itertuples()], index=weather.index)
    weather['wd_sin'] = np.sin(weather['Weekday'] * (2. * np.pi / 7))
    weather['wd_cos'] = np.cos(weather['Weekday'] * (2. * np.pi / 7))
    weather['hr_sin'] = np.sin(weather['Hour'] * (2. * np.pi / 24))
    weather['hr_cos'] = np.cos(weather['Hour'] * (2. * np.pi / 24))
    weather['mnth_sin'] = np.sin((weather['Month'] - 1) * (2. * np.pi / 12))
    weather['mnth_cos'] = np.cos((weather['Month'] - 1) * (2. * np.pi / 12))
    try:
        weather['Temp'] = weather['Temp (°C)']
        weather['Dew Point Temp'] = weather['Dew Point Temp (°C)']
        weather.drop(['Rel Hum Flag', 'Wind Dir (10s deg)', 'Wind Dir Flag', 'Wind Spd (km/h)',
                      'Wind Spd Flag', 'Visibility (km)', 'Visibility Flag', 'Temp Flag', 'Dew Point Temp Flag',
                      'Stn Press (kPa)', 'Stn Press Flag', 'Hmdx Flag', 'Wind Chill', 'Rel Hum (%)', 'Hmdx',
                      'Dew Point Temp',
                      'Wind Chill Flag', 'Weather', 'Temp (°C)', 'Dew Point Temp (°C)'], 1, inplace=True)
    except Exception as e:
        pass
    return weather
def new_deg_days(df):
    """

    takes a temperature from a dataframe and returns two lists that correspond
    to its heat and cool degree days (from 6 degress C)

    :param df: input dataframe with a temperature column
    :return: two lists. 1st: heat degree day. 2nd: cool degree day
    """
    newdata = [i[4] for i in df.itertuples()]

    heatdays = [6-x for x in newdata]
    cooldays = [x-6 for x in newdata]
    newheatdays=[]
    newcooldays=[]
    for x in heatdays:
        if x < 0:
            newheatdays.append(0)
        else:
            newheatdays.append(x)
    for x in cooldays:
        if x < 0:
            newcooldays.append(0)
        else:
            newcooldays.append(x)
    return newheatdays,newcooldays
def pull_historical_data(city = 'Toronto', year = 2014, freq = None):
    weatherpath = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
    weatherdb = '{}WeatherHistorical.db'.format(city.replace(' ', ''))
    conn2 = sqlite3.connect(weatherpath + weatherdb)
    if freq == 'D':
        weather = pd.read_sql('Select * from {} where YEAR >= {}'.format(citydict[city]['tablename']+ '_Daily', year), conn2,
                              index_col='DATETIME')
    else:
        weather = pd.read_sql('Select * from {} where YEAR >= {}'.format(citydict[city]['tablename'], year), conn2,
                              index_col='DATETIME')
    weather.index = pd.to_datetime(weather.index)
    return weather

# download data from Weather Canada and put into databases
def load_2019_data_hourly(month=1):
    """

    appends to database hourly weather data from jan 1, 2019 onward
    :return: nothing


    """
    for z in list(citydict.keys()):
        today = datetime.datetime.now()
        bigdf = get_new_data_hourly(citydict[z]['stationid'], 2019, month)
        bigdf = bigdf[bigdf.index < datetime.datetime(today.year, today.month, today.day-1, 5)]
        path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
        db = '{}WeatherHistorical.db'.format(z.replace(' ', ''))
        conn = sqlite3.connect(path + db)
        bigdf.to_sql(citydict[z]['tablename'], conn, index=True, if_exists='append')
        print(z, 'done')
def load_old_data_into_db_hourly():
    """
    replaces database for weather with all data from 2011 - 2018 that is available. Hourly
    :return: nothing
    """
    for z in list(citydict.keys()):
        dfs = {}
        for x in range(2011, 2019):
            for y in range(1, 13):
                try:
                    dfs['{}_{}'.format(x, y)] = get_new_data_hourly(citydict[z]['stationid'], x, y)
                    print(z, x, y)
                    time.sleep(2)
                except Exception as e:
                    print(str(e))
                    pass
        bigdf = pd.concat([x for x in dfs.values()])
        bigdf.drop_duplicates(inplace=True)
        engine = azure_sql_connection()
        bigdf.to_sql(citydict[z]['tablename'], engine, index=True, if_exists='replace')
        print(z, 'done')
def load_old_data_into_db_daily():
    """
    replaces database for weather with all data from 2011 - 2018 that is available. Hourly
    :return: nothing
    """
    for z in list(citydict.keys()):
        dfs = {}
        for x in range(2011, 2020):
            try:
                dfs['{}'.format(x)] = get_new_data_daily(citydict[z]['stationid'], x)
                print(z, x)
            except Exception as e:
                print(str(e))
                pass
        bigdf = pd.concat([x for x in dfs.values()])
        bigdf.drop_duplicates(inplace=True)
        today = datetime.datetime.now()
        bigdf = bigdf[bigdf.index < datetime.datetime(today.year, today.month, today.day)]
        engine = azure_sql_connection()
        bigdf.to_sql(citydict[z]['tablename']+'_Daily', engine, index=True, if_exists='replace')
        print(z, 'done')
def get_new_data_daily(stationid, year=None):
    """
    grab most recent data (this year) from Weather Canada in csv form. The dataframe is sorted, column datatypes assigned
    and many columns are dropped.

    :param stationid: station ID to grab from
    :param year: year
    :return: returns a dataframe that's cleaned
    """

    date = datetime.datetime.now()
    if year:
        datastring = f"http://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={stationid}&Year={year}&Month=1&Day=14&timeframe=2&submit=Download+Data.csv"
    else:
        datastring = f"http://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={stationid}&Year={date.year}&Month=1&Day=14&timeframe=2&submit=Download+Data.csv"
    df = pd.read_csv(datastring)
    df.columns = df.columns.str.replace('\(°C\)', '')
    df.columns = df.columns.str.strip()
    df.columns = df.columns.str.upper()
    cols = ['Date/Time', 'Year', 'Month','Day','Max Temp','Min Temp','Mean Temp','Total Precip (mm)']
    Wdata = df[[x.upper() for x in cols]]
    Wdata.rename({'DATE/TIME': 'DATETIME', 'MAX TEMP':'MAX_TEMP','MIN TEMP':'MIN_TEMP','MEAN TEMP':'MEAN_TEMP', 'TOTAL PRECIP (MM)':'TOTAL_PRECIP_MM'},axis = 'columns', inplace = True)
    Wdata.dropna(thresh=4, inplace=True)
    Wdata.fillna(method='ffill', inplace=True)
    Wdata.fillna(method='bfill', inplace=True)
    Wdata.set_index('DATETIME', inplace=True)

    Wdata.index = pd.to_datetime(Wdata.index)
    Wdata = Wdata[Wdata.index < datetime.datetime.now()-datetime.timedelta(days=1)]
    Wdata = Wdata.sort_index()

    return Wdata
def get_new_data_hourly(stationid, year=None, month = None):
    """
    grab most recent data (this month) from Weather Canada in csv form. The dataframe is sorted, column datatypes assigned
    and extra columns HOUR and HUMIDEX are added, while many are dropped

    :param stationid: station ID to grab from
    :param year: year
    :param month: month
    :return: returns a dataframe that's cleaned
    """
    date = datetime.datetime.now()
    if year and month:
        datastring = f"http://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={stationid}&Year={year}&Month={month}&Day=14&timeframe=1&submit=Download+Data.csv"
    else:
        datastring = f"http://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={stationid}&Year={date.year}&Month={date.month}&Day=14&timeframe=1&submit=Download+Data.csv"
    df = pd.read_csv(datastring, encoding='utf-8',  names=['DATETIME', 'YEAR', 'MONTH', 'DAY', 'Time', 'TEMP', 'Temp Flag',
                            'DEW_TEMP', 'Dew Point Temp Flag', 'REL_HUM', 'Rel Hum Flag',
                            'Wind Dir (10s deg)', 'Wind Dir Flag', 'Wind Spd (km/h)', 'Wind Spd Flag',
                            'Visibility (km)', 'Visibility Flag', 'Stn Press (kPa)', 'Stn Press Flag',
                            'Hmdx', 'Hmdx Flag', 'Wind Chill', 'Wind Chill Flag', 'Weather'])
    Wdata = df[['DATETIME', 'YEAR', 'MONTH', 'DAY', 'TEMP', 'REL_HUM', 'DEW_TEMP']]
    Wdata.fillna(method='ffill', inplace=True)
    Wdata.fillna(method='bfill', inplace=True)
    Wdata.set_index('DATETIME', inplace=True)
    Wdata.index = pd.to_datetime(Wdata.index)
    Wdata = Wdata.sort_index()
    Wdata['HOUR'] = Wdata.index.hour
    Wdata['HUMIDEX'] = pd.Series([hmdxx(x.TEMP, x.DEW_TEMP) for x in Wdata.itertuples()], index=Wdata.index)
    Wdata['REL_HUM'] = Wdata['REL_HUM'].astype(np.int64)
    return Wdata
def add_latest_historical(stationid, z, conn, year=None, month = None):
    """
    grab most recent data (this month) from Weather Canada in csv form. The dataframe is sorted, column datatypes assigned
    and extra columns HOUR and HUMIDEX are added, while many are dropped. Only returns from latest timestamp in DB to newest in csv.

    :param stationid: station ID to grab from
    :param year: year
    :param month: month
    :return: returns a dataframe that's cleaned
    """

    def read_latest_demand_datetime(conn, tablename):
        query = """select datetime from {}""".format(tablename)
        new = pd.read_sql(query, conn)
        return new.max()

    latest_dt = read_latest_demand_datetime(conn, citydict[z]['tablename'])
    latest_dt_datetime = datetime.datetime(int(latest_dt.values[0][:4]), int(latest_dt.values[0][5:7]), int(latest_dt.values[0][8:10]), int(latest_dt.values[0][11:13]))
    if year and month:
        datastring = "http://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={}&Year={}&Month={}&Day=14&timeframe=1&submit=Download+Data.csv".format(
        stationid, year, month)
    try:
        df = pd.read_csv(datastring, encoding='utf-8', skiprows=16, header=None,
                         names=['DATETIME', 'YEAR', 'MONTH', 'DAY', 'Time', 'TEMP', 'Temp Flag',
                                'DEW_TEMP', 'Dew Point Temp Flag', 'REL_HUM', 'Rel Hum Flag',
                                'Wind Dir (10s deg)', 'Wind Dir Flag', 'Wind Spd (km/h)', 'Wind Spd Flag',
                                'Visibility (km)', 'Visibility Flag', 'Stn Press (kPa)', 'Stn Press Flag',
                                'Hmdx', 'Hmdx Flag', 'Wind Chill', 'Wind Chill Flag', 'Weather'])
        Wdata = df[['DATETIME', 'YEAR', 'MONTH', 'DAY', 'TEMP', 'REL_HUM', 'DEW_TEMP']]
        Wdata.set_index('DATETIME', inplace=True)
        Wdata.index = pd.to_datetime(Wdata.index)
    except:
        df = pd.read_csv(datastring, encoding='utf-8', skiprows=17, header=None,
                         names=['DATETIME', 'YEAR', 'MONTH', 'DAY', 'Time', 'TEMP', 'Temp Flag',
                                'DEW_TEMP', 'Dew Point Temp Flag', 'REL_HUM', 'Rel Hum Flag',
                                'Wind Dir (10s deg)', 'Wind Dir Flag', 'Wind Spd (km/h)', 'Wind Spd Flag',
                                'Visibility (km)', 'Visibility Flag', 'Stn Press (kPa)', 'Stn Press Flag',
                                'Hmdx', 'Hmdx Flag', 'Wind Chill', 'Wind Chill Flag', 'Weather'])
        Wdata = df[['DATETIME', 'YEAR', 'MONTH', 'DAY', 'TEMP', 'REL_HUM', 'DEW_TEMP']]
        Wdata.set_index('DATETIME', inplace=True)
        Wdata.index = pd.to_datetime(Wdata.index)
    Wdata.dropna(how='any', inplace=True)
    Wdata = Wdata.loc[latest_dt_datetime + datetime.timedelta(hours=1):, :]
    Wdata = Wdata.sort_index()
    Wdata['TEMP'] = Wdata['TEMP'].astype(float)
    Wdata['DEW_TEMP'] = Wdata['DEW_TEMP'].astype(float)
    Wdata['HOUR'] = Wdata.index.hour
    Wdata['HUMIDEX'] = pd.Series([hmdxx(x.TEMP, x.DEW_TEMP) for x in Wdata.itertuples()], index=Wdata.index)
    Wdata['REL_HUM'] = Wdata['REL_HUM'].astype(np.int64)
    return Wdata
def load_latest_data_into_db_hourly():
    """
    Updates DBs with newest data since the last timestamp. Hourly
    :return: nothing
    """
    today = datetime.datetime.now()
    credentials = get_credentials()
    dbschema = 'dbo,schema,public,online'  # Searches left-to-right
    connection_string = "Driver={ODBC Driver 17 for SQL Server};" + "Server={};Database={};Uid={};Pwd={};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryPassword".format(
        credentials[0], credentials[1], credentials[2], credentials[3])
    engine = create_engine("mssql+pyodbc:///?odbc_connect={}".format(urllib.parse.quote_plus(connection_string)),
                           connect_args={'options': '-csearch_path={}'.format(dbschema)})
    path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
    for z in list(citydict.keys()):
        db = '{}WeatherHistorical.db'.format(z.replace(' ', ''))
        conn = sqlite3.connect(path + db)
        bigdf = add_latest_historical(citydict[z]['stationid'], z, conn, int(today.year), int(today.month))
        bigdf.drop_duplicates(inplace=True)
        bigdf.to_sql(citydict[z]['tablename'], conn, index=True, if_exists='append')
        bigdf.to_sql(citydict[z]['tablename'], engine, index=True, if_exists='append')
        logging.info(str(z) + ' Hourly:  done')
        logging.info('Last two lines: ')
        logging.info(bigdf.tail(2).to_string())
def load_latest_data_into_db_daily():
    """
    Updates DBs with newest data since the last timestamp. Hourly
    :return: nothing
    """
    # Azure SQL DB
    credentials = get_credentials()
    dbschema = 'dbo,schema,public,online'  # Searches left-to-right
    connection_string = "Driver={ODBC Driver 17 for SQL Server};" + "Server={};Database={};Uid={};Pwd={};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryPassword".format(
        credentials[0], credentials[1], credentials[2], credentials[3])
    engine = create_engine("mssql+pyodbc:///?odbc_connect={}".format(urllib.parse.quote_plus(connection_string)),
                           connect_args={'options': '-csearch_path={}'.format(dbschema)})
    for y in citydict.keys():
        all_data = get_new_data_daily(citydict[y]['stationid'])
        all_data = all_data.iloc[-1:, :]
        all_data.to_sql(citydict[y]['tablename'] + '_Daily', engine, if_exists='append')
        logging.info(str(y) + 'Daily:  done')
        logging.info('Last line: ')
        logging.info(all_data.to_string())

# previous day's hourly weather scripts
def create_table_previous_hourly(c_, nameOfTable):
    """
    convenient function to create a table

    :param c_: connection to database
    :param nameOfTable: name of table in database
    :return: nothing
    """
    c_.execute(
        "CREATE TABLE IF NOT EXISTS {}(DATETIME TEXT, YEAR SMALLINT, MONTH TINYINT, DAY TINYINT, HOUR TINYINT, TEMP REAL, DEW_TEMP REAL, REL_HUM REAL, HUMIDEX REAL)".format(
            '"' + nameOfTable + '"'))
def data_entry_previous_hourly(c_, nameOfTable, DATETIME, YEAR, MONTH, DAY, HOUR, TEMP, DEW_TEMP, REL_HUM, HUMIDEX):
    """

    adding data to the table, the variables are self-explanatory

    :param c_: connection the the database
    :param nameOfTable: name of the table to add the row
    :param DATETIME:
    :param YEAR:
    :param MONTH:
    :param DAY:
    :param HOUR:
    :param TEMP:
    :param DEW_TEMP:
    :param REL_HUM:
    :param HUMIDEX:
    :return: nothing
    """
    c_.execute(
        'INSERT INTO {} VALUES("{}",{},{},{},{},{},{},{},{})'.format('"' + nameOfTable + '"', DATETIME, YEAR, MONTH,
                                                                     DAY, HOUR, TEMP, DEW_TEMP, REL_HUM, HUMIDEX))
def get_previous_day_weather_hourly(city, stationid, tablename):
    """

    Automates adding new data to each of the database tables. if process cannot complete, tries again in 2 minutes, if still not complete, sends an email
    to work address.

    :param city: city to work on
    :param stationid: station id of said city
    :param tablename: table name for the city
    :return: nothing
    """

    def getpreviousdayweatherinner():
        path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
        db = '{}WeatherHistorical.db'.format(city.replace(' ', ''))
        conn = sqlite3.connect(path + db)
        c2 = conn.cursor()
        date = datetime.datetime.now()
        Wdata = get_new_data_hourly(stationid)
        # Wdata2 = Wdata[Wdata['Day'] == date.day - 1]
        aa = Wdata[(Wdata['DAY'] == (date.day - 1)) | (Wdata['DAY'] == (date.day - 2))]
        bb = aa[aa.index > datetime.datetime(date.year, date.month, date.day - 2, 4)]
        cc = bb[bb.index < datetime.datetime(date.year, date.month, date.day - 1, 5)]
        nameofTable = tablename

        for x in cc.itertuples():
            data_entry_previous_hourly(c2, nameofTable, DATETIME=x.Index, YEAR=x.YEAR, MONTH=x.MONTH, DAY=x.DAY,
                                      HOUR=x.HOUR,
                                      TEMP=x.TEMP, DEW_TEMP=x.DEW_TEMP, REL_HUM=x.REL_HUM, HUMIDEX=x.HUMIDEX)
        conn.commit()
        conn.close()
        copy2(path + db,'H:/python/weatherdata/' + db)
        logging.info("{} database copied to shared folder!".format(city.upper()))
        logging.info("{} got yesterday's data!".format(city.upper()))

    try:
        getpreviousdayweatherinner()
    except Exception as e:
        try:
            logging.info(str(e))
            logging.info('retrying in 2 minutes...')
            time.sleep(180)
            getpreviousdayweatherinner()
        except Exception as ee:
            logging.info(str(ee))
            send_email(text='Error in {} WEATHER PREVIOUS script'.format(city.upper()),
                       html='Error in {} WEATHER PREVIOUS script'.format(city.upper()))
def gather_previous_day_weather_hourly():
    """
    function to run 'getpreviousdayweather' for each city in the citydict
    :return: nothing
    """
    for x in citydict.keys():
        get_previous_day_weather_hourly(x, citydict[x]['stationid'], citydict[x]['tablename'])

# previous day's daily weather scripts
def create_table_previous_daily(c_, nameOfTable):
    """
    convenient function to create a table

    :param c_: connection to database
    :param nameOfTable: name of table in database
    :return: nothing
    """
    c_.execute(
        "CREATE TABLE IF NOT EXISTS {}(DATETIME TEXT, YEAR SMALLINT, MONTH TINYINT, DAY TINYINT, MAX_TEMP REAL, MIN_TEMP REAL, MEAN_TEMP REAL, TOTAL_PRECIP REAL)".format(
            '"' + nameOfTable + '"'))
def data_entry_previous_daily(c_, nameOfTable, DATETIME, YEAR, MONTH, DAY, MAX_TEMP, MIN_TEMP, MEAN_TEMP, TOTAL_PRECIP):
    """

    adding data to the table, the variables are self-explanatory

    :param c_: connection the the database
    :param nameOfTable: name of the table to add the row
    :param DATETIME:
    :param YEAR:
    :param MONTH:
    :param DAY:
    :param MAX_TEMP:
    :param MIN_TEMP:
    :param MEAN_TEMP:
    :param TOTAL_PRECIP:
    :return: nothing
    """
    c_.execute(
        'INSERT INTO {} VALUES("{}",{},{},{},{},{},{},{})'.format('"' + nameOfTable + '"', DATETIME, YEAR, MONTH,
                                                                     DAY, MAX_TEMP, MIN_TEMP, MEAN_TEMP, TOTAL_PRECIP))
def get_previous_day_weather_daily(city, stationid, tablename):
    """

    Automates adding new data to each of the database tables. if process cannot complete, tries again in 2 minutes, if still not complete, sends an email
    to work address.

    :param city: city to work on
    :param stationid: station id of said city
    :param tablename: table name for the city
    :return: nothing
    """

    def getpreviousdayweatherinner():
        path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
        db = '{}WeatherHistorical.db'.format(city.replace(' ', ''))
        conn = sqlite3.connect(path + db)
        c2 = conn.cursor()
        date = datetime.datetime.now()
        Wdata = get_new_data_daily(stationid)
        Wdata = Wdata[Wdata.index == datetime.datetime(date.year, date.month, date.day - 1)]
        nameofTable = tablename

        for x in Wdata.itertuples():
            data_entry_previous_daily(c2, nameofTable, DATETIME=x.Index, YEAR=x.YEAR, MONTH=x.MONTH, DAY=x.DAY,
                                       MAX_TEMP=x.MAX_TEMP, MIN_TEMP=x.MIN_TEMP, MEAN_TEMP=x.MEAN_TEMP, TOTAL_PRECIP = x.TOTAL_PRECIP)
        conn.commit()
        conn.close()
        copy2(path + db,'H:/python/weatherdata/' + db)
        logging.info("{} (Daily) database copied to shared folder!".format(city.upper()))
        logging.info("{} (Daily) got yesterday's data!".format(city.upper()))

    try:
        getpreviousdayweatherinner()
    except Exception as e:
        try:
            logging.info(str(e))
            logging.info('retrying in 2 minutes...')
            time.sleep(180)
            getpreviousdayweatherinner()
        except Exception as ee:
            logging.info(str(ee))
            send_email(text='Error in {} WEATHER PREVIOUS DAILY script'.format(city.upper()),
                       html='Error in {} WEATHER PREVIOUS DAILY script'.format(city.upper()))
def gather_previous_day_weather_daily():
    """
    function to run 'getpreviousdayweather' for each city in the citydict
    :return: nothing
    """
    for x in citydict.keys():
        get_previous_day_weather_daily(x, citydict[x]['stationid'], citydict[x]['tablename']+ '_Daily')

# forecast scripts
def data_entry_forecast(c_, nameOfTable, timee, temp, feels, humidity, date):
    """

    inserts into table specified all of the values corresponding to the forecast

    :param c_: database connection
    :param nameOfTable: name of table to update
    :param timee: time of forcasted temp
    :param temp: temp in celsius
    :param feels: feels like (humidex temp)
    :param humidity: relative humidity level
    :param date: date of the forecast
    :return: nothing
    """

    c_.execute(
        'INSERT INTO {} VALUES("{}",{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{},{})'.format(
            '"' + nameOfTable + '"', str(date).split('.')[0],
            timee[0], temp[0], feels[0], humidity[0],
            timee[1], temp[1], feels[1], humidity[1],
            timee[2], temp[2], feels[2], humidity[2],
            timee[3], temp[3], feels[3], humidity[3],
            timee[4], temp[4], feels[4], humidity[4],
            timee[5], temp[5], feels[5], humidity[5],
            timee[6], temp[6], feels[6], humidity[6],
            timee[7], temp[7], feels[7], humidity[7],
            timee[8], temp[8], feels[8], humidity[8],
            timee[9], temp[9], feels[9], humidity[9],
            timee[10], temp[10], feels[10], humidity[10],
            timee[11], temp[11], feels[11], humidity[11],
            timee[12], temp[12], feels[12], humidity[12],
            timee[13], temp[13], feels[13], humidity[13],
            timee[14], temp[14], feels[14], humidity[14],
            timee[15], temp[15], feels[15], humidity[15]))
def create_table_forecast(nameOfTable):
    c2.execute("""CREATE TABLE IF NOT EXISTS {} (CURRENTTIME TEXT, 
                CURRENTHOUR SMALLINT, CURRENTHOURTEMP SMALLINT, CURRENTHOURFEELS SMALLINT, CURRENTHOURHUMIDITY SMALLINT,
                SECONDHOUR SMALLINT, SECONDHOURTEMP SMALLINT, SECONDHOURFEELS SMALLINT, SECONDHOURHUMIDITY SMALLINT,
                THIRDHOUR SMALLINT, THIRDHOURTEMP SMALLINT, THIRDHOURFEELS SMALLINT, THIRDHOURHUMIDITY SMALLINT,
                FOURTHHOUR SMALLINT, FOURTHHOURTEMP SMALLINT, FOURTHHOURFEELS SMALLINT, FOURTHHOURHUMIDITY SMALLINT,
                FIFTHHOUR SMALLINT, FIFTHHOURTEMP SMALLINT, FIFTHHOURFEELS SMALLINT, FIFTHHOURHUMIDITY SMALLINT,
                SIXTHHOUR SMALLINT, SIXTHHOURTEMP SMALLINT, SIXTHHOURFEELS SMALLINT, SIXTHHOURHUMIDITY SMALLINT,
                SEVENTHHOUR SMALLINT, SEVENTHHOURTEMP SMALLINT, SEVENTHHOURFEELS SMALLINT, SEVENTHHOURHUMIDITY SMALLINT,
                EIGHTHHOUR SMALLINT, EIGHTHHOURTEMP SMALLINT, EIGHTHHOURFEELS SMALLINT, EIGHTHHOURHUMIDITY SMALLINT,
                NINTHHOUR SMALLINT, NINTHHOURTEMP SMALLINT, NINTHHOURFEELS SMALLINT, NINTHHOURHUMIDITY SMALLINT,
                TENTHHOUR SMALLINT, TENTHHOURTEMP SMALLINT, TENTHHOURFEELS SMALLINT, TENTHHOURHUMIDITY SMALLINT,
                ELEVENTHHOUR SMALLINT, ELEVENTHHOURTEMP SMALLINT, ELEVENTHHOURFEELS SMALLINT, ELEVENTHHOURHUMIDITY SMALLINT,
                TWELFTHHOUR SMALLINT, TWELFTHHOURTEMP SMALLINT, TWELFTHHOURFEELS SMALLINT, TWELFTHHOURHUMIDITY SMALLINT,
                THIRTEENTHHOUR SMALLINT, THIRTEENTHHOURTEMP SMALLINT, THIRTEENTHHOURFEELS SMALLINT, THIRTEENTHHOURHUMIDITY SMALLINT,
                FOURTEENTHHOUR SMALLINT, FOURTEENTHHOURTEMP SMALLINT, FOURTEENTHHOURFEELS SMALLINT, FOURTEENTHHOURHUMIDITY SMALLINT,
                FIFTEENTHHOUR SMALLINT, FIFTEENTHHOURTEMP SMALLINT, FIFTEENTHHOURFEELS SMALLINT, FIFTEENTHHOURHUMIDITY SMALLINT,
                SIXTEENTHHOUR SMALLINT, SIXTEENTHHOURTEMP SMALLINT, SIXTEENTHHOURFEELS SMALLINT, SIXTEENTHHOURHUMIDITY SMALLINT)""".format(
        '"' + nameOfTable + '"'))
def gather_weather_forecast_hourly(citytimezone, nameofcity, url):
    """

    Go to weather.com's website and scrape the forecast - should be 16 values of each. Tries for 5 minutes
    initially, then 2.5 minutes, then sends an email stating that there was an error.

    :param citytimezone: timezone of the city
    :param nameofcity: name of the city
    :param url: partial url of the site to scrape from
    :return: nothing
    """

    try:
        date = datetime.datetime.now().astimezone(pytz.timezone(citytimezone))
        name = '{}_Weather_Forecast'.format(nameofcity.replace(' ', '_'))
        path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
        conn = sqlite3.connect(path + '{}weather.db'.format(nameofcity.replace(' ', '')))
        c2 = conn.cursor()
        # parse the Weather Channel's webpage and pulls forecasted weather data
        request = Request('https://weather.com/en-CA/weather/hourbyhour/l/{}'.format(url),
                          headers={'User-Agent': 'Mozilla/5.0'})
        graphsource = urlopen(request).read()
        soup = bs.BeautifulSoup(graphsource, 'html.parser')  # actual and predicted data
        timee = []
        temp = []
        feels = []
        humidity = []
        table = soup.find_all('tr')
        for x in table:
            for y in x.find_all('td'):
                if y.get('headers') == ['time']:
                    timee.append(y.text)
                if y.get('headers') == ['temp']:
                    temp.append(y.text)
                if y.get('headers') == ['feels']:
                    feels.append(y.text)
                if y.get('headers') == ['humidity']:
                    humidity.append(y.text)
        # these variables are for the weather data
        timee = [int(x.replace('\n', '').split(':')[0]) for x in timee]
        temp = [int(x.split('°')[0]) for x in temp]
        feels = [int(x.split('°')[0]) for x in feels]
        humidity = [x.split('%')[0] for x in humidity]

        # col_headers = [
        #                "CURRENTHOUR", "CURRENTHOURTEMP", "CURRENTHOURFEELS", "CURRENTHOURHUMIDITY",
        #                "SECONDHOUR", "SECONDHOURTEMP", "SECONDHOURFEELS", "SECONDHOURHUMIDITY",
        #                "THIRDHOUR", "THIRDHOURTEMP", "THIRDHOURFEELS", "THIRDHOURHUMIDITY",
        #                "FOURTHHOUR", "FOURTHHOURTEMP", "FOURTHHOURFEELS", "FOURTHHOURHUMIDITY",
        #                "FIFTHHOUR", "FIFTHHOURTEMP", "FIFTHHOURFEELS", "FIFTHHOURHUMIDITY",
        #                "SIXTHHOUR", "SIXTHHOURTEMP", "SIXTHHOURFEELS", "SIXTHHOURHUMIDITY",
        #                "SEVENTHHOUR", "SEVENTHHOURTEMP", "SEVENTHHOURFEELS", "SEVENTHHOURHUMIDITY",
        #                "EIGHTHHOUR", "EIGHTHHOURTEMP", "EIGHTHHOURFEELS", "EIGHTHHOURHUMIDITY",
        #                "NINTHHOUR", "NINTHHOURTEMP", "NINTHHOURFEELS", "NINTHHOURHUMIDITY",
        #                "TENTHHOUR", "TENTHHOURTEMP", "TENTHHOURFEELS", "TENTHHOURHUMIDITY",
        #                "ELEVENTHHOUR", "ELEVENTHHOURTEMP", "ELEVENTHHOURFEELS", "ELEVENTHHOURHUMIDITY",
        #                "TWELFTHHOUR", "TWELFTHHOURTEMP", "TWELFTHHOURFEELS", "TWELFTHHOURHUMIDITY",
        #                "THIRTEENTHHOUR", "THIRTEENTHHOURTEMP", "THIRTEENTHHOURFEELS", "THIRTEENTHHOURHUMIDITY",
        #                "FOURTEENTHHOUR", "FOURTEENTHHOURTEMP", "FOURTEENTHHOURFEELS", "FOURTEENTHHOURHUMIDITY",
        #                "FIFTEENTHHOUR", "FIFTEENTHHOURTEMP", "FIFTEENTHHOURFEELS", "FIFTEENTHHOURHUMIDITY",
        #                "SIXTEENTHHOUR", "SIXTEENTHHOURTEMP", "SIXTEENTHHOURFEELS", "SIXTEENTHHOURHUMIDITY"]
        # data = pd.DataFrame()
        # data['Time'] = [int(str(x).replace('\n', '').split(':')[0]) for x in timee]
        # data['Time'] = data['Time'].astype(int)
        # data['Temp'] = [int(str(x).split('°')[0]) for x in temp]
        # data['Feels'] = [int(str(x).split('°')[0]) for x in feels]
        # data['Humidity'] = [str(x).split('%')[0] for x in humidity]
        # data['Temp'] = data['Temp'].astype(int)
        # data['Feels'] = data['Feels'].astype(int)
        # data['Humidity'] = data['Humidity'].astype(int)
        #
        # new = pd.concat([pd.DataFrame(data.iloc[x,:]).T for x in range(len(data.index))], axis='columns')
        # new.fillna(method='ffill', inplace=True)
        # alt_data = pd.DataFrame([new.values[-1]], columns=col_headers, index=[str(date).split('.')[0]])
        # print(name, alt_data.to_string())
        try:
            # schema needs to be specified (usually dbo) or else no commit happens
            data_entry_forecast(c2, name, timee, temp, feels, humidity, date)
            conn.commit()
            logging.info('{} WEATHER FORECAST table updated! Local time: {}'.format(nameofcity.upper(), date))
        except Exception as q:
            print('fails {} | {}'.format(str(q), error_handling()))
            logging.info(str(q))
            logging.info(
                '{} WEATHER FORECAST FAILED! Trying again in 5 minutes. Local time: {}'.format(nameofcity.upper(),
                                                                                               date))
            time.sleep(300)
            try:
                data_entry_forecast(c2, name, timee, temp, feels, humidity, date)
                conn.commit()
                logging.info('{} WEATHER FORECAST table updated! Local time: {}'.format(nameofcity.upper(), date))
            except Exception as i:
                logging.info(str(i))
                logging.info(
                    '{} WEATHER FORECAST FAILED! Trying again in 2.5 minutes. Local time: {}'.format(nameofcity.upper(),
                                                                                                     date))
                time.sleep(150)
                try:
                    data_entry_forecast(c2, name, timee, temp, feels, humidity, date)
                    conn.commit()
                    logging.info('{} WEATHER FORECAST table updated! Local time: {}'.format(nameofcity.upper(), date))
                except Exception as ii:
                    logging.info(str(ii) + "| email sent")
                    send_email(text='Error in {} WEATHER FORECAST script | {} | {}'.format(nameofcity.upper(), str(ii), error_handling()),
                               html='Error in {} WEATHER FORECAST script | {} | {}'.format(nameofcity.upper(), str(ii), error_handling()))
    except Exception as e:
        logging.info(str(e) + "| email sent")
        send_email(text='Error in {} WEATHER FORECAST script | {} | {}'.format(nameofcity.upper(), str(e), error_handling()),
                   html='Error in {} WEATHER FORECAST script | {} | {}'.format(nameofcity.upper(), str(e), error_handling()))
def gather_weather_forecasts():
    """

    runs 'gatherweatherforecastupdated' for each city

    :return: nothing
    """
    for x in citiesdict.keys():
        gather_weather_forecast_hourly(citiesdict[str(x)]['timezone'], x, citiesdict[str(x)]['url'])
def copy_weather_forecast_to_azure():
    credentials = get_credentials()
    dbschema = 'dbo,schema,public,online'  # Searches left-to-right
    connection_string = "Driver={ODBC Driver 17 for SQL Server};" + "Server={};Database={};Uid={};Pwd={};Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;Authentication=ActiveDirectoryPassword".format(
        credentials[0], credentials[1], credentials[2], credentials[3])
    engine = create_engine("mssql+pyodbc:///?odbc_connect={}".format(urllib.parse.quote_plus(connection_string)),
                           connect_args={'options': '-csearch_path={}'.format(dbschema)})
    path = r'C:/Users/J_Ragbeer/PycharmProjects/weatherdata/'
    for z in list(citiesdict.keys()):
        name = '{}_Weather_Forecast'.format(z.replace(' ', '_'))
        db = '{}weather.db'.format(z.replace(' ', ''))
        conn = sqlite3.connect(path + db)
        new = pd.read_sql('select * from {}'.format(name), conn)
        new.drop_duplicates(inplace=True)
        new.to_sql(name, engine, index=False, if_exists='replace')
        logging.info('{} copy complete'.format(name))
def hourly_forecast_24(citytimezone, nameofcity, url, q):
    def grab_soup(url_, browser="firefox"):
        """
        This function enables a driver (using Firefox or Chrome), goes to the URL, and retrieves the data after the JS is loaded.

        :param url_: url to go to to retrieve data
        :param browser: browser to use, defaults to firefox (requires geckodriver.exe on path)
        :return:

        soup - the data of the page
        driver - the browser (process) instance
        """
        if browser == 'chrome':
            chromeOptions = chrome_options()
            chromeOptions.add_experimental_option("prefs", {
                "download.default_directory": r"C:\Users\J_Ragbeer\Downloads",
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            })
            chromeOptions.add_argument("--disable-gpu")
            chromeOptions.add_argument("--headless")
            driver = webdriver.Chrome(options=chromeOptions)
        else:
            firefoxOptions = firefox_options()
            firefoxOptions.set_preference("browser.download.folderList", 2)
            firefoxOptions.set_preference("browser.download.manager.showWhenStarting", False)
            firefoxOptions.set_preference("browser.download.dir", path.replace('/', '\\') + 'data\\downloads\\')
            firefoxOptions.set_preference("browser.helperApps.neverAsk.saveToDisk",
                                          "application/octet-stream,application/vnd.ms-excel,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            driver = webdriver.Firefox(options=firefoxOptions)

        driver.get(url_)  # go to the URL
        html = driver.page_source
        time.sleep(1)  # sleep for 1 second  to ensure all JS scripts are loaded
        html = driver.execute_script("return document.body.outerHTML;")  # execute javascript code
        soup_ = bs.BeautifulSoup(html, 'lxml')  # read the data as html (using lxml driver)
        return soup_, driver
    try:
        datee = datetime.datetime.now().astimezone(pytz.timezone(citytimezone))
        name = '{}_Weather_Forecast_24'.format(nameofcity.replace(' ', '_'))
        path = os.getcwd().replace("\\", "/") + "/"
        conn = sqlite3.connect(path + '{}weather.db'.format(nameofcity.replace(' ', '')))
        engine = azure_sql_connection()
        soup, web_driver = grab_soup(url, )
        # allow all elements to load
        time.sleep(22)
        web_driver.find_element_by_xpath("""//*[@id="twc-scrollabe"]/div/button""").click()
        # allow all elements to load
        time.sleep(23)
        timee = []
        temp = []
        feels = []
        humidity = []
        precip = []
        wind = []
        # reload html after JS interaction
        html_after_click = web_driver.page_source
        soup = bs.BeautifulSoup(html_after_click, 'html.parser')
        # find the table and parse it
        table = soup.find_all('tr')
        for x in table:
            for y in x.find_all('td'):
                if y.get('headers') == ['time']:
                    timee.append(y.text)
                if y.get('headers') == ['temp']:
                    temp.append(y.text)
                if y.get('headers') == ['feels']:
                    feels.append(y.text)
                if y.get('headers') == ['humidity']:
                    humidity.append(y.text)
                if y.get('headers') == ['precip']:
                    precip.append(y.text)
                if y.get('headers') == ['wind']:
                    wind.append(y.text)
        # these variables are for the weather data
        timee = [int(x.replace('\n', '').split(':')[0]) for x in timee]
        temp = [int(x.split('°')[0]) for x in temp]
        feels = [int(x.split('°')[0]) for x in feels]
        humidity = [int(x.split('%')[0]) for x in humidity]
        precip = [int(x.split('%')[0]) for x in precip]
        wind = [0 if x.upper() == 'CALM' else int(x.split('km/h')[0].split(' ')[1].strip()) for x in wind]
        # wind = [int(x.split('km/h')[0].split(' ')[1].strip()) for x in wind]
        # wind = [int(x.split('km/h')[0]) for x in wind]
        # create names of columns in dataframe
        hours = ['current', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth',
                 'nineth', 'tenth', 'eleventh', 'twelfth', 'thirteenth', 'fourteenth', 'fifteenth',
                 'sixteenth', 'seventeenth', 'eighteenth', 'nineteenth', 'twentieth', 'twentyfirst',
                 'twentysecond', 'twentythird']
        capture_list = ['hour', 'temp', 'feels', 'humidity', 'precip', 'wind']
        column_names = ["CURRENT_TIME"] + [str(x + '_hour_' + i).upper() for x in hours for i in capture_list]
        # create blank data frame from column names
        df = pd.DataFrame({ii: 0 for ii in column_names}, index=[0])
        all_values = [each_list[hr] for hr in range(len(timee)) for each_list in
                      [timee, temp, feels, humidity, precip, wind]]
        # update each column with data, including current time
        for x in range(1, len(df.columns)):
            df.iloc[0, x] = all_values[x - 1]
        df.iloc[0, 0] = str(datee).split('.')[0]
        # add to databases, local and in Azure
        df.to_sql(name, conn, if_exists='append', index=False)
        df.to_sql(name, engine, if_exists='append', index=False)
        web_driver.quit()  # after all files are downloaded, close the browser instance
        try:
            q.put('over')  # message to send to the queue - if run in standalone, does nothing.
        except:
            pass
    except:
        web_driver.quit()
        print(error_handling())
        sys.exit()
def gather_weather_forecasts_24():
    """
    This function runs each of the data extraction scripts concurrently.
    :return: nothing
    """
    q = mp.Queue()  # put each process on a queue, so when finished,
    new = {}
    for city in citiesdict.keys():
        URL = f'https://weather.com/en-CA/weather/hourbyhour/l/{citiesdict[city]["url"]}'
        new[city] = Process(target=hourly_forecast_24,
                     args=(citiesdict[city]["timezone"], city, URL, q,))  # assign process X the function
        new[city].start()  # start processes

    procs = []
    while True:  # check if processes are finished every 8 seconds
        time.sleep(1)
        procs.append(q.get())
        if len(procs) == len(list(citiesdict.keys())):  # once all processes are complete, break loop
            break
    if procs == ['over' * len(list(citiesdict.keys()))]:  # if all 3 processes finish successfully, terminate them
        for x in new:
            new[x].terminate()
    # join the processes so that they (and the parent process) finish and release resources at the same time
    for x in new:
        new[x].join()
    q.close()  # close the queue (release resources)

# send an email / error handling
def send_email(text, html):
    """

    Logs on to gmail via smtp and sends an email containing the html verison along with the subject to the senders in the function

    if hmtl version doesn't send for some reason, reverts to the text version.

    :param text: body or message of the email in natural text
    :param html: body or message of the email in html formatting
    :return: nothing
    """
    # This is a temporary fix. Be careful of malicious links
    context = ssl._create_unverified_context()

    curtime = datetime.datetime.now()  # current time and date

    # list of who to send the email to
    TO = ['jragbeer@oxfordproperties.com']
    SUBJECT = 'Error in a Weather script'  # subject line of the email

    TEXT = text
    HTML = html

    # Gmail Sign In
    gmail_sender = 'julienwork789@gmail.com'  # senders email
    gmail_passwd = '12fork34'  # senders password

    msg = MIMEMultipart('alternative')  # tell the package we'd prefer HTML emails
    msg['Subject'] = SUBJECT  # set the SUBJECT of the email
    msg['From'] = gmail_sender  # set the FROM field of the email
    msg['To'] = ', '.join(TO)  # set the TO field of the email

    part1 = MIMEText(TEXT, 'plain')  # add the 2 parts of the email (one plain text, one html)
    part2 = MIMEText(HTML, 'html')
    msg.attach(part1)  # It will default to the plain text verison if the HTML doesn't work, plain must go first
    msg.attach(part2)

    server = smtplib.SMTP_SSL('smtp.gmail.com', 465)  # connect to the GMAIL server
    server.login(gmail_sender, gmail_passwd)  # login to the GMAIL server

    try:
        server.sendmail(gmail_sender, TO, msg.as_string())  # send email
        logging.info('email sent')  # confirm email is sent, and the time
    except Exception as e:
        logging.info(str(e))  # print error if not sent
        logging.info('error sending mail')  # confirm that email wasn't sent

    server.quit()
def error_handling():
    """

    This function returns a string with all of the information regarding the error

    :return: string with the error information
    """
    return traceback.format_exc()

#for the weather forecasts
citiesdict = {'Toronto': {'url':'CAXX0504:1:CA', 'timezone': 'America/Toronto'},
              'Boston': {'url':'USMA0046:1:US', 'timezone': 'America/Toronto'},
              'Berlin': {'url':'10785:4:GM', 'timezone': 'Europe/Berlin'},
              'Vancouver':{'url':'CAXX0518:1:CA', 'timezone': 'America/Vancouver'},
              'Mississauga': {'url':'CAXX0295:1:CA', 'timezone': 'America/Toronto'},
              'Edmonton': {'url':'CAXX0126:1:CA', 'timezone': 'America/Edmonton'},
              'Montreal': {'url':'CAXX0301:1:CA', 'timezone': 'America/Toronto'},
              'Gatineau': {'url':'CAXX0158:1:CA', 'timezone': 'America/Toronto'},
              'Calgary': {'url':'CAXX0054:1:CA', 'timezone': 'America/Edmonton'},
              'Washington DC': {'url':'USDC0001:1:US', 'timezone': 'America/Toronto'},
                'Brossard': {'url':'CAXX1183:1:CA', 'timezone': 'America/Toronto'},
            'Quebec City': {'url':'CAXX0385:1:CA', 'timezone': 'America/Toronto'},
            'New York City': {'url':'10022:4:US', 'timezone': 'America/Toronto'}}

# for the previous day's official weather
citydict = {
'Toronto':{'stationid': 48549, 'tablename': 'Toronto_City_Center'},
'Vancouver':{'stationid': 888, 'tablename': 'Vancouver_Harbour_CS'},
'Calgary':{'stationid': 50430, 'tablename': 'Calgary_INTL_A'},
'Edmonton':{'stationid': 53718, 'tablename': 'Edmonton_South_Campus'},
'Brossard':{'stationid': 48374, 'tablename': 'Montreal_St_Hubert'},
'Montreal':{'stationid': 30165, 'tablename': 'Montreal_Pierre_Elliot_Trudeau_INTL'},
'Gatineau':{'stationid': 50719, 'tablename': 'Ottawa_Gatineau_A'},
'Quebec City':{'stationid': 51457, 'tablename': 'Quebec_INTL_A'},
'Mississauga':{'stationid': 51459, 'tablename': 'Toronto_INTL_A'}}

