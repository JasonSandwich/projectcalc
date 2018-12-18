#!/usr/bin/env python
# -*- coding: UTF-8 -*-
# Created by Jonas Gulle
# Modified by Martin Holmström

from bs4 import BeautifulSoup, Tag
from urllib2 import urlopen
from operator import itemgetter
from decimal import *
import datetime
import mysql.connector

# Change to your db host, username etc
db = mysql.connector.connect(host='127.0.0.1', user='pcars', passwd='<insertyourpassword>', db='pcarsdb') # change to your values
cur = db.cursor()

URL="http://cars2-stats-steam.wmdportal.com/index.php"

class ProjectCARS2(object):
	def __init__(self, baseurl=URL):
		self.baseurl = baseurl
		self.soup = self.__get_soup(baseurl)
		self.track_by_name = self.__get_tracks()
		self.track_by_id = self.invert_dict(self.track_by_name)
		self.vehicle_by_name = self.__get_vehicles()
		self.vehicle_by_id = self.invert_dict(self.vehicle_by_name)

	def invert_dict(self, d):
		return {v: k for k, v in d.iteritems()}

	def __get_soup(self, url):
		page = urlopen(url)
		soup = BeautifulSoup(page, "lxml")
		page.close()
		return soup

	def __get_vehicles(self):
		select = self.__tags(self.soup.find(attrs={"id": "select_leaderboard_vehicle", "name": "vehicle"}))
		vehicles = {}
		dupe_counter = 1
		for option in select:
			# Test if the car is a duplicate (such as the Audi R18 and some others)
			if option.text in vehicles:
				# If there is a duplicate, append an underscore and integer to the vehicle name
				vehicles["%s_%d" % (option.text, dupe_counter)] = int(option["value"])
				dupe_counter += 1
			else:
				vehicles[option.text] = int(option["value"])
		return vehicles	
		
	def __get_tracks(self):
		select = self.__tags(self.soup.find(attrs={"id": "select_leaderboard_track", "name": "track"}))
		tracks = {}
		for option in select:
			tracks[option.text] = int(option["value"])
		return tracks

	def __tags(self, coll):
		return filter(lambda x: isinstance(x, Tag), coll)

	# Return the sector times in milliseconds.
	def get_sector_times(self, td):
		times = td["title"]
		sector_times = []
		# Test if null
		if (td["title"]) == "":
			td["title"] = "Sector 1: 0:00.000\nSector 2: 0:00.000\nSector 3: 0:00.000"
		for sector, mins, secs in (x.split(":") for x in td["title"].split("\n")):
			ms = int(mins)*60*1000
			secs = secs.split(".")
			ms += int(secs[0])*1000 + int(secs[1])
			sector_times.append(ms)			
		return sector_times

	# Return the sum of all sector times in "m:ss.nnn"
	def format_time(self, sector_times):
		global laptime
		ms = sum(sector_times) if isinstance(sector_times, list) else sector_times
		laptime = (Decimal(ms) / 1000)
		# return "%02d:%02d.%03d" % (ms/(60*1000), (ms/1000)%60, ms%1000)
		return laptime

	def get_leaderboard(self, track, vehicle=0, index=1):
		track = int(track)
		vehicle = int(vehicle)
		page = urlopen(self.baseurl + "/leaderboard?track=%d&vehicle=%d&page=%d" % (track, vehicle, index))
		soup = BeautifulSoup(page, "lxml")
		page.close()

		def get_td(tr, name):
			return tr.find("td", {"class": name})

		table = soup.find("table", id="leaderboard")
		leaderboard = []
		for tr in self.__tags(table.tbody.findAll("tr")):
			sector_times = self.get_sector_times(get_td(tr, "time"))
			
			# Get setup: Custom or Default
			global setup
			setup = tr.find('td', {'class': 'assists'}).img.get('alt')
			setup = setup[7:]
			
			#Get controller: Wheel, Gamepad or Keyboard
			global controller
			controller = tr.findAll('img')[2]['title']
			controller = controller[12:]
				
			#Get camera: In-car or External
			global camera
			camera = tr.findAll('img')[3]['title']
			camera = camera[8:]
			
			leaderboard.append({
				"rank": get_td(tr, "rank").text,
				"user": get_td(tr, "user").text.strip(),
				"sector_times": sector_times,
				"time": self.format_time(sector_times),
				"vehicle": get_td(tr, "vehicle").text if vehicle == 0 else self.vehicle_by_id[vehicle],
				"gap": get_td(tr, "gap").text,
				"timestamp": get_td(tr, "timestamp").text
			})

		# Test for more pages
		if len(leaderboard) == 100:
			leaderboard += self.get_leaderboard(track, vehicle, index+1)

			
		return sorted(leaderboard, key=itemgetter("time"))
		
	def store_leaderboard(self,lb):
	# In database, create unique_index(track,carname,player,laptime) to stop from inserting duplicates, thanks to INSERT IGNORE
		sql = "INSERT IGNORE INTO laptimes (track, gamertag, laptime, vehicle, sessionmode, lapdate, sector1, sector2, sector3, platform, setup, controller, camera) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
		for row in lb:
			# Get sector times in seconds
			S1 = (Decimal(row["sector_times"][0]) / 1000)
			S2 = (Decimal(row["sector_times"][1]) / 1000)
			S3 = (Decimal(row["sector_times"][2]) / 1000)
			# Format date 
			setdate = datetime.datetime.strptime(row["timestamp"], "%d/%m/%Y %H:%M").strftime("%Y-%m-%d %H:%M")						
			# Define what values are stored (same order as %s above)
			val = (current_track, row["user"], row["time"], current_vehicle, "Time Trial", setdate, S1, S2, S3, "PC", setup, controller, camera)
			
			cur.execute(sql, val)
			
		print(cur.rowcount, "record inserted.")	
		db.commit()
		
	#def print_leaderboard(self, lb):
		
		#for row in lb:		
			
			#print "%s: %-25.25s %s %s %s" % (
			#	row["rank"],
			# 	row["user"],
			# 	row["time"],
			# 	row["vehicle"],
			# 	row["gap"]
			#)
		
def main():
	pc2 = ProjectCARS2()
	
	# Download the complete leaderboard for selected entries
	customtracks = {("Watkins Glen International GP","2509185801"),("Brands Hatch Indy","1300627020"),("Oulton Park International","545979690"),("Sportsland SUGO","3270746104"),("Nurburgring Nordschleife","697498609")}
	customvehicles = {("BMW 2002 StanceWorks Edition","3107219035"),("Ginetta G40 Junior","310900789"),("Radical SR3-RS","1231996358"),("Ford MkIV","2520631554"),("Lamborghini Huracan GT3","4201933325"),("Formula Renault 3.5","1626504761"), }
	# To add laptimes for a new car, uncomment and change row(s) below, so no need to rescrape everything. Same can be done for a new track.
	# customtracks = {} 
	# customvehicles = {("Audi R18 (Le Mans 2016)","4054224091")}
	# lb = pc2.get_leaderboard(1988984740, 1639105598)
	# pc2.store_leaderboard(lb)
	
	# Loop through each car for first track, then 2nd track and so on
	for track_name, track_id in customtracks:
		print "Track name: %s" % track_name
		global current_track
		current_track = track_name
		global vehicle
		global vehicle_id
		for  vehicle, vehicle_id in customvehicles:
			print "Vehicle: %s " % vehicle
			global current_vehicle
			current_vehicle = vehicle
			try:
				# print vehicle_id, track_id
				lb = pc2.get_leaderboard(track_id, vehicle_id)
				pc2.store_leaderboard(lb)
			except TypeError:
				print "This leaderboard contains no data"
				
	
	"""for track_name, track_id in pc2.track_by_name.iteritems():
		try:
			print "Storing leaderboard for %s [overall best]" % track_name
			global current_track
			current_track = track_name
			pc2.store_leaderboard(pc2.get_leaderboard(track_id))
			# print "Getting leaderboard for %s [overall best]" % track_name
			# pc2.print_leaderboard(pc2.get_leaderboard(track_id))
		except TypeError:
			print "This leaderboard contains no data"
		#  raw_input()"""

	return 0
	cur.close()
 	db.close()
if __name__ == "__main__":
	exit(main())
	
	
	
# 
# ("24 Hours of Le Mans Circuit","1740968730"),
# ("Autodromo Internazionale Enzo E Dino Ferrari Imola","920145926"),
# ("Autodromo Nazionale Monza GP","4241994684"),
# ("Autodromo Nazionale Monza GP Historic","1184596327"),
# ("Autodromo Nazionale Monza Historic Oval + GP Mix","1327182267"),
# ("Autodromo Nazionale Monza Oval Historic","4131920659"),
# ("Autodromo Nazionale Monza Short","368740158"),
# ("Autodromo Internacional do Algarve","3878349996"),
# ("Azure Circuit","832629329"),
# ("Azure Coast","560711985"),
# ("Azure Coast Stage 1","550129415"),
# ("Azure Coast Stage 2","3514087720"),
# ("Azure Coast Stage 3","2557706171"),
# ("Azure Coast Westbound","2358176792"),
# ("Bannochbrae Road Circuit","3692283027"),
# ("Barcelona Rallycross","1828877100"),
# ("Bathurst Mount Panorama","921120824"),
# ("Brands Hatch GP","1988984740"),
# ("Brands Hatch Indy","1300627020"),
# ("Brno GP","3387066030"),
# ("Cadwell Park Club","328972919"),
# ("Cadwell Park GP","1876749797"),
# ("Cadwell Park Woodland","2886778255"),
# ("California Highway Full","2701023129"),
# ("California Highway Reverse","928006536"),
# ("California Highway Stage 1","1676943041"),
# ("California Highway Stage 2","940391868"),
# ("California Highway Stage 3","3963464445"),
# ("Chesterfield Karting Circuit","2559054883"),
# ("Circuit de Barcelona-Catalunya Club","3252038398"),
# ("Circuit de Barcelona-Catalunya GP","521933422"),
# ("Circuit de Barcelona-Catalunya National","3296775302"),
# ("Circuit de Spa-Francorchamps GP","904625875"),
# ("Circuit de Spa-Francorchamps Historic","2490004715"),
# ("Circuit of the Americas Club","802214179"),
# ("Circuit of the Americas GP","2050315946"),
# ("Circuit of the Americas National","1629467388"),
# ("Classic Brands Hatch Rallycross","2239809056"),
# ("Daytona International Speedway Rallycross","35770107"),
# ("Daytona International Speedway Tri-Oval","2054003546"),
# ("Daytona Road Course","467707118"),
# ("DirtFish Boneyard Course","980779751"),
# ("DirtFish Mill Run Course","2600030656"),
# ("DirtFish Pro Rallycross Course","2186625931"),
# ("Donington Park GP","354022214"),
# ("Donington Park National","3100947921"),
# ("Dubai Autodrome Club","1735854797"),
# ("Dubai Autodrome GP","3633079779"),
# ("Dubai Autodrome International","3584254603"),
# ("Dubai Autodrome National","4263239849"),
# ("Dubai Kartdrome","4062453922"),
# ("Fuji GP","2599752939"),
# ("Glencairn East","766599953"),
# ("Glencairn East Reverse","3848172327"),
# ("Glencairn GP","3228224516"),
# ("Glencairn Reverse","2774122716"),
# ("Glencairn West","2886187703"),
# ("Glencairn West Reverse","3381341938"),
# ("Greenwood Karting Circuit","3134524219"),
# ("Hockenheim Classic GP","1552853772"),
# ("Hockenheim GP","1695182971"),
# ("Hockenheim National","2317824311"),
# ("Hockenheim Rallycross","761864750"),
# ("Hockenheim Short","1768660198"),
# ("Indianapolis Motor Speedway Oval","62242453"),
# ("Indianapolis Motor Speedway Road Course","211444010"),
# ("Knockhill International","2168579513"),
# ("Knockhill International Reverse","3206894082"),
# ("Knockhill National","1887425815"),
# ("Knockhill National Reverse","458589160"),
# ("Knockhill Rallycross","977699253"),
# ("Knockhill Tri-Oval","3353861064"),
# ("Le Mans Bugatti Circuit","3267032607"),
# ("Le Mans International Karting Circuit","1457129528"),
# ("Le Mans Vintage Track","167552033"),
# ("Long Beach Street Circuit","1731699995"),
# ("Lydden Hill GP","953639515"),
# ("Lydden Hill Rallycross","673609283"),
# ("Lankebanen Rallycross","2087662703"),
# ("Mazda Raceway Laguna Seca","2682943968"),
# ("Mercedes-Benz Driving Events Ice Track 1","3387498244"),
# ("Mercedes-Benz Driving Events Ice Track 2","1365171965"),
# ("Mercedes-Benz Driving Events Ice Track 3","3569358649"),
# ("Mercedes-Benz Driving Events Ice Track 4","480123345"),
# ("Mercedes-Benz Driving Events Ice Track 5","2208202376"),
# ("Mercedes-Benz Driving Events Ice Track Full","4291750443"),
# ("Mojave Boa Ascent","3310957537"),
# ("Mojave Cougar Ridge","31280808" )
# ("Mojave Coyote Noose","369271528"),
# ("Mojave Gila Crest","4234466862"),
# ("Mojave Sidewinder","2015693491"),
# ("Mugello GP","1730519219"), 
# ("Nurburgring Combined","3403453048"),
# ("Nurburgring GP","3348999902"),
# ("Nurburgring Mullenbach","4048000896"),
# ("Nurburgring Nordschleife","697498609"),
# ("Nurburgring Nordschleife Stage 1","1459212514"),
# ("Nurburgring Nordschleife Stage 2","3994580005"),
# ("Nurburgring Nordschleife Stage 3","1128950148"),
# ("Nurburgring Sprint","3585230195"),
# ("Nurburgring Sprint Short","3484251453"),
# ("Oschersleben A Course","3100781576"),
# ("Oschersleben B Course","816601966"),
# ("Oschersleben C Course","2935667702"),
# ("Oulton Park Fosters","2273942801"),
# ("Oulton Park International","545979690"),
# ("Oulton Park Island","2417267773"),
# <option value="1371913179">Pista di Fiorano</option>	
# ("Porsche Leipzig Dynamic Circuit","4189064524"),
# ("Porsche Leipzig Full Circuit","4136123652"),
# ("Porsche Leipzig Short Circuit","169281142"),
# ("Rallycross of Loheac","3696088069"),
# ("Red Bull Ring Club","4221780682"),
# ("Red Bull Ring GP","2361713765"),
# ("Red Bull Ring National","2280743555"),
# ("Road America","3634666530"),
# ("Rouen Les Essarts","3263717367"),
# ("Rouen Les Essarts Short","2779493388"),
# ("Ruapuna Park A Circuit","619694160"),
# ("Ruapuna Park B Circuit","2248334206"),
# ("Ruapuna Park Club","1446378877"),
# ("Ruapuna Park GP","1277693448"),
# ("Ruapuna Park Outer Loop","1940584155"),
# ("Sakitto GP","2535224250"),
# ("Sakitto International","2820797104"),
# ("Sakitto National","3034141030"),
# ("Sakitto Sprint","3415685177"),
# ("Sampala Ice Circuit","3471919275"),
# ("Silverstone Classic GP","3100676468"),
# ("Silverstone GP","1641471184"),
# ("Silverstone International","1101719627"),
# ("Silverstone National","1952936927"),
# ("Silverstone Stowe","1600840139"),
# ("Snetterton 100","3427627286"),
# ("Snetterton 200","1058872832"),
# ("Snetterton 300","1508903068"),
# ("Sonoma Raceway GP","2840687665"),
# ("Sonoma Raceway National","3299764567"),
# ("Sonoma Raceway Short","1035110721"),
# ("Sportsland SUGO","3270746104"),
# ("Summerton International","4250218976"),
# ("Summerton National","1408845203"),
# ("Summerton Sprint","2689053728"),
# ("Texas Motor Speedway","1185954707"),
# ("Texas Motor Speedway Infield Course","1719717729"),
# ("Texas Motor Speedway Road Course","533066470"),
# ("Watkins Glen International GP","2509185801"),
# ("Watkins Glen International Short","1590386668"),
# ("Wildcrest Rallycross","1892852585"),
# ("Willow Springs Horse Thief Mile","2445435734"),
# ("Willow Springs International Raceway","4191654388"),
# ("Zhuhai International Circuit","1836888499"),
# ("Zolder","3934256239"),
#  
#   
# ("Acura NSX","728234598"),
# ("Acura NSX GT3","3416883430"), 
# ("Agajanian Watson Roadster","2851776933"), 
# ("Aston Martin DB11","2991153806"), 
# ("Aston Martin DBR1/300","4203152210"), 
# ("Aston Martin Vantage GT12","1268015922"), 
# ("Aston Martin Vantage GT3","1452261378"), 
# ("Aston Martin Vantage GT4","2086246081"), 
# ("Aston Martin Vantage GTE","1401532035"), 
# ("Aston Martin Vulcan","1682144078"), 
# ("Audi 90 quattro IMSA GTO","1470929381"), 
# ("Audi A1 quattro","2082176226"), 
# ("Audi R18 (Fuji 2016)","3088285373"), 
# ("Audi R18 (Le Mans 2016)","4054224091"), 
# ("Audi R18 e-tron quattro","1219511257"), 
# ("Audi R8","2533296245"), 
# ("Audi R8 LMS","1934199723"), 
# ("Audi R8 LMS Endurance","998894988"), 
# ("Audi R8 V10 plus 5.2 FSI quattro","1469658023"), 
# ("Audi S1 EKS RX quattro","2155160105"), 
# ("Audi Sport quattro S1","2702065929"), 
# ("Audi V8 quattro DTM","3954590596"), 
# ("BAC Mono","1400443574"), 
# ("Bentley Continental GT3 (2015)","987814806"), 
# ("Bentley Continental GT3 (2016)","3293302308"), 
# ("Bentley Continental GT3 Endurance","1637772163"), 
# ("Bentley Speed 8","3800867225"), 
# ("BMW 1 Series M Coupe","3068790356"), 
# ("BMW 1 Series M Coupe StanceWorks Edition","2883643484"), 
# ("BMW 2002 StanceWorks Edition","3107219035"), 
# ("BMW 2002 Turbo","143364290"), 
# ("BMW 320 TC","9503224"), 
# ("BMW 320 Turbo Group 5","779111340"), 
# ("BMW M1 Procar","1368036017"), 
# ("BMW M3 GT4","2749517114"), 
# ("BMW M3 Sport Evo Group A","3360868789"), 
# ("BMW M6 GT3","4053780148"), 
# ("BMW M6 GTLM","3512434557"), 
# ("BMW V12 LMR","975104023"), 
# ("BMW Z4 GT3","1161219858"), 
# ("Cadillac ATS-V.R GT3","2269735930"), 
# ("Caterham Seven 620 R","1864701845"), 
# ("Caterham SP/300.R","675194619"), 
# ("Chevrolet Camaro Z/28 '69 TransAm","728095309"), 
# ("Chevrolet Camaro ZL-1","178583869"), 
# ("Chevrolet Corvette C7.R","3910923019"), 
# ("Chevrolet Corvette Z06","1141733552"), 
# ("Citroen DS3 RX Supercar","3311961229"), 
# ("Dallara IR-12 Chevrolet (Speedway)","1818067169"), 
# ("Dallara IR-12 Chevrolet (Road Course)","3912454102"), 
# ("Dallara IR-12 Honda (Road Course)","2498938793"), 
# ("Dallara IR-12 Honda (Speedway)","2230297826"), 
# ("Datsun 280ZX IMSA GTX","3406832937"), 
# ("Ferrari 250 GT Berlinetta","3889953946"), 
# ("Ferrari 250 Testa Rossa","3542185868"),
# ("Ferrari 288 GTO","2392626889"), 
# ("Ferrari 330 P4","3959862335"), 
# ("Ferrari 333 SP","3021002396"), 
# ("Ferrari 365 GTB4 Competizione","696555869"), 
# ("Ferrari 458 Speciale A","2006190056"), 
# ("Ferrari 488 Challenge (EU)","1471547500"), 
# ("Ferrari 488 Challenge (APAC)","754463374"), 
# ("Ferrari 488 Challenge (NA)","345014385"), 
# ("Ferrari 488 GT3","185812116"), 
# ("Ferrari 488 GTE","405826415"), 
# ("Ferrari 512 BB LM","1317086096"), 
# ("Ferrari 512 M","2463819442"), 
# ("Ferrari 512 S","3654776849"), 
# ("Ferrari Enzo","2835431732"), 
# ("Ferrari F12tdf","3789350886"), 
# ("Ferrari F355 Challenge","2574370663"), 
# ("Ferrari F40","2327134663")
# ("Ferrari F40 LM","1015579264"), 
# ("Ferrari F50 GT","2566143295"), 
# ("Ferrari FXX ","220908396"),
# ("Ferrari LaFerrari","1965567405"), 
# ("Ford Bronco Brocky","1830085946"), 
# ("Ford Escort RS1600 (Racing)","3679780595"), 
# ("Ford Escort RS1600","1639105598"), 
# ("Ford Escort RS1600 (Rallycross)","2498018106"), 
# ("Ford F-150 RTR Ultimate Funhaver","2746026001"), 
# ("Ford Falcon FG V8 Supercar","1357515789"), 
# ("Ford Focus RS RX","647968520"), 
# ("Ford Fusion Stockcar","851491257"), 
# ("Ford GT","366881611"), 
# ("Ford GT LM GTE","2438214702"), 
# ("Ford MkIV","2520631554"), 
# ("Ford Mustang '66 RTR TransAm","3921573780"), 
# ("Ford Mustang 2+2 Fastback","1397255601"), 
# ("Ford Mustang Boss 302R","1111049682"), 
# ("Ford Mustang Cobra TransAm","4283632081"), 
# ("Ford Mustang GT","1230061845"), 
# ("Ford Mustang RTR GT4","161704608"), 
# ("Ford Mustang RTR Spec - 5D","3941218963"), 
# ("Ford RS200 Evolution Group B","375801487"), 
# ("Ford Sierra Cosworth RS500 Group A","3041492578"), 
# ("Formula A","1909945073"), 
# ("Formula C","3253292325"), 
# ("Formula Renault 3.5","1626504761"), 
# ("Formula Rookie","2219682419"), 
# ("Formula X","3855427461"), 
# ("Ginetta G40 GT5","58065064"), 
# ("Ginetta G40 Junior","310900789"),
# ("Ginetta G55 GT3","3124293020"), 
# ("Ginetta G55 GT4","2091910841"), 
# ("Ginetta G57","1433352906"), 
# ("Ginetta LMP3","3671020568"), 
# ("Honda 2&amp;4 Concept","3846538056"), 
# ("Honda Civic Coupe GRC","951815226"), 
# ("Honda Civic Type-R","373960596"), 
# ("Jaguar E-Type V12 Group44","3289024725"), 
# ("Jaguar F-Type SVR Coupe","1187826685"), 
# ("Jaguar XJ220 S","3907921441"), 
# ("Jaguar XJR-9","1716535504"), 
# ("Jaguar XJR-9 LM","2806835898"), 
# ("Kart","844159614"), 
# ("KTM X-Bow GT4","1574251638"), 
# ("KTM X-Bow R","761457895"), 
# ("Lamborghini Aventador LP700-4","1977120176"), 
# ("Lamborghini Diablo GTR","3097547507"), 
# ("Lamborghini Huracan GT3","4201933325"), 
# ("Lamborghini Huracan LP610-4","1850232477"), 
# ("Lamborghini Huracan LP620-2 Super Trofeo","1406411897"), 
# ("Lamborghini Sesto Elemento","266758367"), 
# ("Lamborghini Veneno LP750-4","1564669712"), 
# ("Ligier JS P2 Honda","1468371103"), 
# ("Ligier JS P2 Judd","3226251087"), 
# ("Ligier JS P2 Nissan","820529698"), 
# ("Ligier JS P3","2343505719"), 
# ("Lotus Type 25 Climax","3581682802"), 
# ("Lotus Type 38 Ford","1162971218"), 
# ("Lotus Type 40 Ford","3090278997"), 
# ("Lotus Type 49 Cosworth","578969971"), 
# ("Lotus Type 49C Cosworth","1061494025"), 
# ("Lotus Type 51","2859910117"), 
# ("Lotus Type 56","4000197262"), 
# ("Lotus Type 72D Cosworth","2974350450"), 
# ("Lotus Type 78 Cosworth","2459105748"), 
# ("Lotus Type 98T Renault Turbo","1959097924"), 
# ("Marek RP 219D LMP2","3314948224"), 
# ("Marek RP 339H LMP1","1898954187"), 
# ("Mazda MX-5 Radbul","2328906350"), 
# ("McLaren 570S","980572679"), 
# ("McLaren 650S GT3","1153746660"), 
# ("McLaren 720S","1106819298"), 
# ("McLaren F1","307010432"), 
# ("McLaren F1 GTR Long Tail","3293397987"), 
# ("McLaren P1","2546290331"), 
# ("McLaren P1 GTR","2955645152"), 
# ("Mercedes-AMG A 45 4MATIC","2772044758"), 
# ("Mercedes-AMG A 45 SMS-R Rallycross","574354493"), 
# ("Mercedes-AMG A 45 SMS-R Touring","3019822479"), 
# ("Mercedes-AMG C 63 Coupe S","4216135289"), 
# ("Mercedes-AMG GT R","2235371958"), 
# ("Mercedes-AMG GT3","1353949246"), 
# ("Mercedes-Benz 190E 2.5-16 Evolution 2 DTM","262982797"), 
# ("Mercedes-Benz 300 SEL 6.8 AMG","4209306796"), 
# ("Mercedes-Benz 300 SL","1401308680"), 
# ("Mercedes-Benz CLK-LM","1979398129"), 
# ("Mercedes-Benz SLS AMG GT3","274862187"), 
# ("Mini Countryman RX","4225812019"), 
# ("Mitsubishi Lancer Evolution IX FQ360","4145350228"), 
# ("Mitsubishi Lancer Evolution VI SVA","3135001313"), 
# ("Mitsubishi Lancer Evolution VI T.M.E.","460478144"), 
# ("Mitsubishi Lancer Evolution X FQ400","998947753"), 
# ("Nissan 300ZX Turbo IMSA GTS","3590815466"), 
# ("Nissan 300ZX Turbo LM","1747257697"), 
# ("Nissan Fairlady 240ZG GTS-II","1481115672"), 
# ("Nissan GT-R Nismo","85063219"), 
# ("Nissan GT-R Nismo GT3","2878763807"), 
# ("Nissan GTP ZX-Turbo","4275744320"), 
# ("Nissan R390 GT1","3951943788"), 
# ("Nissan R89C","1891730007"), 
# ("Nissan R89C LM","2533887208"), 
# ("Nissan Skyline GT-R (BNR32) Group A","2136103830"), 
# ("Nissan Skyline GT-R (R34) SMS-R","3991375490"), 
# ("Nissan Skyline Super Silhouette","4016661190"), 
# ("Olsbergs MSE RX Supercar Lite","3715710369"), 
# ("Opel Astra TCR","3950216669"), 
# ("Oreca 03 Nissan","4196902797"), 
# ("Pagani Huayra BC","1356687088"), 
# ("Pagani Zonda Cinque Roadster","2677051185"), 
# ("Pagani Zonda Revolucion","3808293256"), 
# ("Panoz Esperante GTR1","3423713365"), 
# ("Porsche 908/03 Spyder","1218201782"), 
# ("Porsche 911 Carrera RSR 2.8","3487780088"), 
# ("Porsche 911 GT1-98","1076438091"), 
# ("Porsche 911 GT3 R","809291220"), 
# ("Porsche 911 GT3 R Endurance","1972396515"), 
# ("Porsche 911 GT3 RS","2161369706"), 
# ("Porsche 911 RSR","2999114098"), 
# ("Porsche 917 LH","2765703167"), 
# ("Porsche 917/10","2771777615"), 
# ("Porsche 917K","2459830780"), 
# ("Porsche 918 Spyder Weissach","3596565664"), 
# ("Porsche 919 Hybrid","3076484049"), 
# ("Porsche 924 Carrera GTP","4083384819"), 
# ("Porsche 935/77","1319185453"), 
# ("Porsche 935/78","3024732648"), 
# ("Porsche 935/78-81","3870535055"), 
# ("Porsche 935/80","1213801406"), 
# ("Porsche 936 Spyder","3788694694"), 
# ("Porsche 959 S","3026936399"), 
# ("Porsche 961","3967020141"), 
# ("Porsche 962C","957632269"), 
# ("Porsche 962C Langheck","4246525161"), 
# ("Porsche Carrera GT","2824100037"), 
# ("Porsche Cayman GT4 Clubsport MR","1464988033"), 
# ("Radical RXC Turbo","3246916419"), 
# ("Radical SR3-RS","1231996358"), 
# ("Radical SR8-RX","152867459"), 
# ("Renault 5 Maxi Turbo","3627124995"), 
# ("Renault Alpine A442B","3595323626"), 
# ("Renault Clio Cup","3646257473"), 
# ("Renault Megane R.S. 275 Trophy-R","3338086070"), 
# ("Renault Megane R.S. SMS-R Rallycross","556202917"), 
# ("Renault Megane R.S. SMS-R Touring","2850335028"), 
# ("Renault Megane Trophy V6","3363376819"), 
# ("Renault Sport R.S. 01","2437969172"), 
# ("Renault Sport R.S. 01 GT3","2434080703"), 
# ("RWD P20 LMP2","1352236476"), 
# ("RWD P30 LMP1","1137321511"), 
# ("Sauber C9 LM Mercedes-Benz","1368545018"), 
# ("Sauber C9 Mercedes-Benz","65306143"), 
# ("Toyota 86","4253159674"), 
# ("Toyota GT-86","4059215692"), 
# ("Toyota GT-86 Rocket Bunny Street","1278633095"), 
# ("Toyota GT-One (1999)","3924299245"), 
# ("Toyota GT-One (1998)","2599532525"), 
# ("Toyota TS040 Hybrid","1810453820"), 
# ("Volkswagen Polo RX Supercar","2037619631"), 
# ("Toyota GT-86 Rocket Bunny GT4","1764851930"), 
# ("Toyota TS050 Hybrid","1083119012"), 
# ("Zakspeed Ford Capri Group 5","1817703058"), 
