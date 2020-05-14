import json
import urllib.request
import requests
import schedule
import time

def getdatabase():
	requestr='https://api.worldofwarships.asia/wows/encyclopedia/ships/?application_id=2b7fe83ad3455ce47818ecb2cb9d5818&fields=tier&language=en&page_no='
	shipdb = requests.get(requestr).json()
	pages = shipdb['meta']['page_total']
	jsonpages={}
	for i in range(pages):
		data=requests.get(requestr+str(i+1)).json()
		data=data['data']
		jsonpages.update(data)
	with open('shipdb.json', 'w') as outfile:
   		json.dump(jsonpages, outfile)

	urllib.request.urlretrieve(
		'https://api.asia.warships.today/json/wows/ratings/warships-today-rating/coefficients',
		'coefficients.json'
		)

schedule.every().day.at("17:37").do(getdatabase)

while True:
	schedule.run_pending()
	time.sleep(1)