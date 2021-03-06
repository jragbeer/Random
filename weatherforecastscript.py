from weatherscripts import *

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s,%(message)s',
                        handlers=[logging.FileHandler("weather_forecast_log.txt"),
                                  logging.StreamHandler()])

    print('Running...') #when code is started, display this in the console
    sched = BlockingScheduler() #set up a scheduling object
    sched.add_job(gather_weather_forecasts, 'cron', minute=18, misfire_grace_time=60*5) #run the weather forecast ingest every half an hour
    sched.add_job(gather_weather_forecasts_24, 'cron', minute=16, misfire_grace_time=60*5) #run the weather forecast ingest every half an hour
    sched.add_job(copy_weather_forecast_to_azure, 'cron', minute=19, misfire_grace_time=60*10) #run the weather forecast ingest every half an hour
    sched.add_job(load_latest_data_into_db_hourly, 'cron', hour=8, misfire_grace_time=60*5) #run the weather forecast ingest every half an hour
    sched.add_job(load_latest_data_into_db_daily, 'cron', hour=8, misfire_grace_time=60*5) #run the weather forecast ingest every half an hour
    sched.start() #start the scheduler

