import numpy as np
import pandas as pd
import re, os
import datetime, time
import traceback
import pickle
from pprint import pprint
import pyarrow
import bs4 as bs
from selenium import webdriver
from selenium.webdriver.firefox.options import Options as firefox_options
from selenium.webdriver.chrome.options import Options as chrome_options
from dateutil import parser
from tqdm import tqdm
from dask.distributed import Client, LocalCluster
import dask.delayed
from bokeh.models import ColumnDataSource

def wrap_in_paragraphs(txt, colour="DarkSlateBlue", size=4):
    """

    This function wraps text in paragraph, bold and font tags - according to the colour and size given.

    :param text: text to wrap in tags
    :param colour: colour of the font
    :param size: size of the font
    :return: string wrapped in html tags
    """
    return f"""<p><b><font color={colour} size={size}>{txt}</font></b></p>"""
def error_handling():
    """
    This function returns a string with all of the information regarding the error
    :return: string with the error information
    """
    return traceback.format_exc()
def get_html_from_page(url,):
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
            chromeOptions.add_argument('--no-sandbox')
            chromeOptions.add_argument('--disable-dev-shm-usage')
            driver = webdriver.Chrome('C:/Users/Julien/PycharmProjects/practice/chromedriver85', options=chromeOptions)
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
        soup, web_driver = grab_soup(url, "chrome" )
        # allow all elements to load
        time.sleep(1)
        # reload html after JS interaction
        html_ = web_driver.page_source
        soup = bs.BeautifulSoup(html_, 'html.parser')
        try:
            return soup
        except:
            print('ERROR')
            return soup.text
    except:
        web_driver.quit()
        print(error_handling())
        sys.exit()
def download_538_data():
    df = pd.read_csv("https://projects.fivethirtyeight.com/soccer-api/club/spi_matches.csv")
    df = df[df['league_id'].isin([2411, 1951, 1869, 1843, 1845, 1854, 1818, 1820])] # EPL, Serie A, La Liga, Ligue 1, MLS, Bundesliga, Europa, UCL
    file_name = today.date().strftime("%Y%m%d") + f"_{today.hour}"
    df.to_parquet(data_path + f"538_data_{file_name}.parquet")
    df.to_parquet(data_path + f"latest.parquet")
@dask.delayed
def get_odds_as_record(df_, test, league):
    try:
        a = get_odds_of_game(test, league)
        tmp_odds_df = a['odds']
        # team names may not map, (team 1 in OddsPortal may not be team 1 in 538) this fixes names across the two datasets
        output = pd.concat([pd.DataFrame(tmp_odds_df.loc['Average', :]).T.rename(columns={i: 'avg_' + i for i in tmp_odds_df.columns}),
                         pd.DataFrame(tmp_odds_df.loc['Highest', :]).T.rename(columns={i: 'max_' + i for i in tmp_odds_df.columns})],
                        axis=1).fillna(method='ffill').fillna(method='bfill').drop_duplicates(subset=['avg_1X', 'max_1X'])
        ind = find_index(df_, a)
        output = pd.concat([output, ind], axis=1).fillna(method='ffill').fillna(method='bfill').drop_duplicates(keep = 'last').reset_index(drop=True)
        if output.at[0, 'team1'] == a['fixed_team1'] or output.at[0, 'team2'] == a['fixed_team2']:
            pass
        elif output.at[0, 'team1'] == a['fixed_team2']:
            output.rename(columns={'avg_1X': 'avg_2X', 'high_1X': 'high_2X',
                                'avg_2X': 'avg_1X', 'high_2X': 'high_1X'}, inplace=True)
        else:
            raise Exception
        return output
    except:
        print(test)
        print(error_handling())
        pprint(a)
        print()
        return pd.DataFrame()
def get_games(league, szn, page):
    try:
        if szn != '':
            szn_ = '-' + str(szn)
        else:
            szn_ = szn
        country = nation_league_mapper[league]
        url = f"https://www.oddsportal.com/soccer/{country}/{league.replace(' ', '-')}{szn_}/results/#/page/{page}/"
        soup = get_html_from_page(url)
        links = soup.find_all('td', {'class': 'name table-participant'})
        hrefs = [x.find('a',href=True)['href'] for x in links]
        return hrefs
    except:
        print('No Data')
        print(url)
        return []
def get_odds_of_game(url, league):
    try:
        URL = "https://www.oddsportal.com" + url + "#double;2"
        soup = get_html_from_page(URL)
        table = soup.find('div', {'id': 'odds-data-table'})
        df = pd.read_html(str(table))[0]
        df = df[(df['Bookmakers'] == "Average") | (df['Bookmakers'] == "Highest")][['Bookmakers', '1X', '12', 'X2']]
        game = soup.find('h1').string
        event_date = parser.parse(soup.find('p', {'class': 'date'}).string.split(',')[1]).date()
        t1 = game.split(' - ')[0]
        t2 = game.split(' - ')[1]
        try:
            odds_team1 = team_name_mapper[t1]
        except:
            odds_team1 = t1
        try:
            odds_team2 = team_name_mapper[t2]
        except:
            odds_team2 = t2
        return {'odds':df.set_index("Bookmakers", drop=True), 'game':game, 'date':event_date, 'league':league, 'team1': t1,'team2': t2, "fixed_team2": odds_team2, "fixed_team1": odds_team1}
    except:
        print('No Data')
        print(url)
        return []
def feature_eng(df, win_prob = 0.75):
    df['prob1_win_tie'] = df['prob1'] + df['probtie']
    df['team1_win_tie'] = [i.score1 >= i.score2 for i in df.itertuples()]
    df['prob2_win_tie'] = df['prob2'] + df['probtie']
    df['team2_win_tie'] = [i.score1 <= i.score2 for i in df.itertuples()]
    k = []
    for i in df.itertuples():
        if i.prob1_win_tie > i.prob2_win_tie:
            if i.prob1_win_tie > win_prob:
                k.append(i.team1_win_tie)
            else:
                k.append(np.nan)
        elif i.prob2_win_tie > i.prob1_win_tie:
            if i.prob2_win_tie > win_prob:
                k.append(i.team2_win_tie)
            else:
                k.append(np.nan)
        else:
            k.append(np.nan)
    df['won_bet'] = k
    df['prob_win_tie'] = df[["prob1_win_tie", "prob2_win_tie"]].max(axis=1)
    # df = df.dropna(subset=[i for i in df.columns if i != 'won_bet']).sort_values('date')
    return df
def clean_df():
    df = pd.read_parquet(data_path + "latest.parquet", )
    df['date'] = pd.to_datetime(df['date'])
    df.drop(columns = ['league_id', "importance1", "importance2"], inplace=True)
    return df
def per_team(df_, team = 'Manchester City', season = (2016, 2020), ):
    try:
        df_ = df_[(df_['season'] >= season[0]) & (df_['season'] <= season[1])].copy()
        df = df_[(df_['team1'] == team) | (df_['team2'] == team)].copy()
        df = df[df['date'] <= today]
        df['prob_win_tie'] = [i.prob1 if i.team1 == team else i.prob2 for i in df.itertuples()] + df['probtie']
        df['win_tie'] = [i.score1 >= i.score2 if i.team1 == team else i.score2 >= i.score1 for i in df.itertuples()]
        df['won_bet'] = [i.win_tie if i.prob_win_tie > 0.7 else np.nan for i in df.itertuples()]
        # print(df.to_string())
        df.dropna(inplace=True)
        # print(df.to_string())
        # print()
        output = {'wins':len([x for x in df['won_bet'].dropna() if x ]), 'num_bets':len([x for x in df['won_bet'].dropna()])}
        output['pct'] = output['wins'] / output['num_bets']
        return {team:output}
    except:
        print(team, season)
        print(error_handling())
        return {}
def gather_game_links_serial():
    haha = {}
    for t in nation_league_mapper.keys():
        haha[t] = {}
        for yr in years:
            haha[t][yr] = []
            for page in range(1, 10):
                haha[t][yr].append(get_games(t, yr, page))
        print(t, datetime.datetime.now() - today)
        pickle_out = open(data_path + "soccer_links.pickle", "wb")
        pickle.dump(haha, pickle_out)
        pickle_out.close()
    for ligue in haha.keys():
        for yr in haha[ligue].keys():
            haha[ligue][yr] = [item for sublist in haha[ligue][yr] for item in sublist]
        haha[ligue]['2020-2021'] = haha[ligue]['']
        del haha[ligue]['']
    pickle_out = open(data_path + "soccer_links.pickle", "wb")
    pickle.dump(haha, pickle_out)
    pickle_out.close()
def find_index(df, a):
    try:
        wow = df[df['league'] == a['league']].copy()
        wow = wow[wow['date'] == pd.to_datetime(a['date'])]
        wow = wow[(wow['team1'] == a['fixed_team1']) | (wow['team1'] == a['fixed_team1']) | (wow['team2'] == a['fixed_team2']) | (wow['team2'] == a['fixed_team2'])]
        return wow[['league','date','team1','team2']]
    except:
        print(wow)

def get_full_cut_df(data_,odf_, ligue, team_, domestic, season, win_prob_, min_odds, bet):
    data_ = feature_eng(data_, win_prob_)
    fdf= data_[(data_['league'] == ligue) & (data_['prob_win_tie'] >= win_prob_)].copy()
    if domestic == 'Domestic':
        fdf = fdf[fdf['league'] == ligue]
    elif domestic == 'Domestic + Europe':
        fdf = fdf[(fdf['league'] == ligue) | (fdf['league'] == "UEFA Champions League") | (fdf['league'] == "UEFA Europa League")]
    else:
        fdf = fdf[(fdf['league'] == "UEFA Champions League") | (fdf['league'] == "UEFA Europa League")]
    if team_ != 'All':
        fdf = fdf[(fdf['team1'] == team_) | (fdf['team2'] == team_)]
    fdf = fdf[(fdf['season'] >= season[0]) & (fdf['season'] <= season[1])].copy()
    fdf.dropna(inplace=True)
    full_data = add_odds_data_to_df(fdf, odf_, bet, min_odds)
    print(full_data.to_string())
    return full_data
def read_pickles_to_df(ligue):
    fun = []
    for i, t in enumerate([f"{ligue.lower().replace('-', '_').replace(' ', '_')}_{i.replace('-', '_').replace(' ', '_')}_season.pickle" for i in [f"{a}-{a + 1}" for a in range(2016, 2025)][:5]]):
        # if i == 4:
        pickle_i = open(data_path + t, "rb")
        fun.append(pickle.load(pickle_i))
    return pd.concat(fun)
def add_odds_data_to_df(df, rdf, bet, min_odds_):
    output = pd.merge(df, rdf, left_on=['league', 'date', 'team1', 'team2'], right_on=['league', 'date', 'team1', 'team2'], how='inner')
    output = output.dropna().reset_index(drop=True)
    qq = []
    odd_list = []
    won = []
    for i in output.itertuples():
        if i.won_bet:
            won.append(True)
            if i.prob1_win_tie == i.prob_win_tie:
                qq.append((bet * float(i.avg_1X)))
                odd_list.append(float(i.avg_1X))
            else:
                qq.append((bet * float(i.avg_X2)))
                odd_list.append(float(i.avg_X2))
        else:
            qq.append(-1 * bet)
            won.append(False)
            if i.prob1_win_tie == i.prob_win_tie:
                odd_list.append(float(i.avg_1X))
            else:
                odd_list.append(float(i.avg_X2))
    data = pd.DataFrame({'per_bet': qq, 'odds': odd_list, 'won_bet': won,}, index=output.index)
    data = data[data['odds']>=min_odds_]
    data['cumsum'] = data['per_bet'].cumsum()
    kk = []
    for t in data.itertuples():
        try:
            if data.at[t.Index - 1, 'cumsum'] < 10:
                kk.append(t.cumsum - bet)
            else:
                kk.append(t.cumsum)
        except:
            kk.append(t.cumsum)
    data['sure'] = kk
    tt = [bet]
    for i in data.itertuples():
        if i.won_bet:
            if tt[-1] == 0:
                tt.append(i.odds * bet)
            elif tt[-1] < 0:
                tt.append(tt[-1] + (bet * i.odds))
            elif tt[-1] > 0:
                tt.append(tt[-1] * i.odds)
        else:
            if tt[-1] == 0:
                tt.append(-bet)
            elif tt[-1] > 0:
                tt.append(0)
            elif tt[-1] == -bet:
                tt.append(-2 * bet)
            else:
                tt.append(1000)
    data['yolo'] = tt[1:]
    data = data.drop(columns=['won_bet'])
    final = data.merge(output, left_index=True, right_index=True)
    final = final.drop(columns=['xg1', "xg2", "nsxg1", "nsxg2", "adj_score1", "adj_score2",])
    return final

path = os.getcwd().replace("\\", "/") + "/"
data_path = path + 'data/soccer_betting/'
today = datetime.datetime.now()
pd.set_option('display.width', 500)
pd.set_option('display.max_columns', None)
print(today)

# download latest data
# download_538_data()
# map league to country for URL
nation_league_mapper = {'bundesliga':'germany', 'premier league':'england', 'serie a':'italy', 'ligue 1':'france', 'europa league':'europe', 'champions league':'europe', 'laliga':'spain'}
# maps 538 league : oddsportal name
league_mapper = {'Barclays Premier League': 'premier league',"French Ligue 1": 'ligue 1', "Italy Serie A":"serie a",
                 "German Bundesliga":"bundesliga", "Spanish Primera Division":'laliga', 'UEFA Europa League': 'europa league', "UEFA Champions League":"champions league"}
# maps Oddsportal name : 538 name
team_name_mapper = {'Cadiz CF':'Cadiz','Atl. Madrid':'Atletico Madrid',"Huesca":"SD Huesca","Granada CF":"Granada","Ath Bilbao":"Athletic Bilbao", "Alaves":"Alaves", "Betis":"Real Betis","Valladolid":"Real Valladolid",
                    'Sevilla':'Sevilla FC',

                    'Stoke':'Stoke City',"Huddersfield":"Huddersfield Town","Cardiff":"Cardiff City","Swansea":"Swansea City", "West Brom":"West Bromwich Albion", "Wolves":"Wolverhampton", "Manchester Utd": "Manchester United", "Leicester": "Leicester City", "Norwich":"Norwich City",
                    "Sheffield Utd": "Sheffield United", "West Ham":"West Ham United", "Tottenham":"Tottenham Hotspur", "Brighton":"Brighton and Hove Albion", "Bournemouth":"AFC Bournemouth"}

# read in 5 seasons (starting in 2016-2017) of URLS for each of the Top 5 leagues + Europa/UCL
years = [f"{a}-{a+1}" for a in range(2016, 2025)][:4] + ['']
pickle_in = open(data_path + "soccer_links.pickle","rb")
data = pickle.load(pickle_in)

win_prob = 0.74

# read in 538 prediction data
df = clean_df()
df = feature_eng(df, win_prob)

# if __name__ == '__main__':
#     # Set-up
#     cluster = LocalCluster(threads_per_worker=8,)
#     client = Client(cluster)
#     league = 'premier league'
#     for yrr in [f"{a}-{a+1}" for a in range(2016, 2025)][:4]:
#         collect = []
#         for num, test in enumerate(data[league][yrr]):
#             if num % 50 == 0 and num > 0:
#                 time.sleep(30)
#             collect.append(get_odds_as_record(df, test, league))
#         final = pd.concat(dask.compute(collect)[0])
#         print(final.to_string())
#         pickle_out = open(data_path + f"{league.replace(' ', '_')}_{yrr.replace('-', '_')}_season.pickle", "wb")
#         pickle.dump(final, pickle_out)
#         pickle_out.close()
#         print(datetime.datetime.now() - today)
#     print(datetime.datetime.now()-today)