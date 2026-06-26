"""
Lenient US-location filter for listing location strings.

Decision order (first match wins):
  1. Explicit US state (abbrev/name) or "United States"/"USA"          -> KEEP
  2. Explicit foreign COUNTRY ("India", "Costa Rica", "United Kingdom") -> DROP
  3. Known US city ("San Francisco", "Seattle", ...)                    -> KEEP
  4. Other foreign signal (region / city / code)                        -> DROP
  5. Anything ambiguous, blank, "Remote", "Hybrid", "3 Locations"       -> KEEP (lenient)

Bias is toward KEEP: a US state always wins ("Vancouver, WA", "Ontario, CA"
= California, "Paris, TX"), and a multi-location string that pairs a foreign
city with a US one ("Bangalore, San Francisco") is kept via step 3. A foreign
COUNTRY (step 2) is checked before US cities so "San Jose, Costa Rica" and
"Dublin, Ireland (Mountain View)" still drop on the explicit country.
"""
import re

US_STATES = {
 'al':'alabama','ak':'alaska','az':'arizona','ar':'arkansas','ca':'california',
 'co':'colorado','ct':'connecticut','de':'delaware','fl':'florida','ga':'georgia',
 'hi':'hawaii','id':'idaho','il':'illinois','in':'indiana','ia':'iowa','ks':'kansas',
 'ky':'kentucky','la':'louisiana','me':'maine','md':'maryland','ma':'massachusetts',
 'mi':'michigan','mn':'minnesota','ms':'mississippi','mo':'missouri','mt':'montana',
 'ne':'nebraska','nv':'nevada','nh':'new hampshire','nj':'new jersey','nm':'new mexico',
 'ny':'new york','nc':'north carolina','nd':'north dakota','oh':'ohio','ok':'oklahoma',
 'or':'oregon','pa':'pennsylvania','ri':'rhode island','sc':'south carolina',
 'sd':'south dakota','tn':'tennessee','tx':'texas','ut':'utah','vt':'vermont',
 'va':'virginia','wa':'washington','wv':'west virginia','wi':'wisconsin','wy':'wyoming',
 'dc':'district of columbia',
}
STATE_ABBR = set(US_STATES.keys())
STATE_NAME = set(US_STATES.values())
US_TOKENS = {'united states','usa','u.s.','u.s.a.','us','america',
             'united states of america'}

FOREIGN_COUNTRIES = {
 'canada','united kingdom','uk','england','scotland','wales','ireland','northern ireland',
 'india','germany','france','netherlands','holland','spain','italy','poland','portugal',
 'sweden','norway','denmark','finland','switzerland','austria','belgium','luxembourg',
 'australia','new zealand','singapore','japan','china','hong kong','taiwan',
 'south korea','korea','philippines','indonesia','malaysia','thailand','vietnam',
 'israel','united arab emirates','uae','saudi arabia','qatar','turkey','turkiye','türkiye',
 'brazil','mexico','argentina','chile','colombia','peru','uruguay','panama','costa rica',
 'south africa','nigeria','kenya','egypt','czechia','czech republic','romania','greece',
 'hungary','ukraine','russia','pakistan','bangladesh','sri lanka','nepal','bulgaria',
 'slovakia','serbia','estonia','slovenia','croatia',
}

# Foreign admin regions: Indian states, Canadian provinces, Chinese provinces, etc.
FOREIGN_REGIONS = {
 # India
 'karnataka','maharashtra','telangana','tamil nadu','haryana','gujarat','kerala',
 'west bengal','uttar pradesh','rajasthan','punjab','andhra pradesh','madhya pradesh',
 'karnātaka',
 # Canada (provinces)
 'ontario','quebec','québec','alberta','manitoba','saskatchewan','nova scotia',
 'new brunswick','newfoundland','british columbia','prince edward island',
 # China (provinces)
 'jiangsu','liaoning','anhui','guangdong','zhejiang','shandong','sichuan','hubei',
 'shaanxi','beijing','shanghai',
 # Other regions
 'noord-brabant','limburg','mazowieckie','pomeranian','lanarkshire','selangor','johor',
 'jakarta raya','victoria','new south wales','nairobi county','wilayah persekutuan',
 'central bohemian','capital region',
}

# Foreign cities — curated to EXCLUDE names that are also notable US cities
# (no Cambridge, Paris, London, Manchester, Birmingham, Waterloo, etc.)
FOREIGN_CITIES = {
 # India
 'bengaluru','bangalore','hyderabad','pune','gurugram','gurgaon','chennai','mumbai',
 'noida','kolkata','new delhi','delhi','ahmedabad','blr','divyasree',
 # China / HK / Taiwan
 'shanghai','beijing','shenzhen','suzhou','hefei','shenyang','zhubei','changshu',
 'zhuhai','guangzhou','chengdu','hong kong','taipei',
 # SE / E Asia
 'tokyo','seoul','jakarta','kuala lumpur','petaling jaya','pasir gudang','bangkok',
 'busan','daegu','manila','alabang','muntinlupa','hanoi','ho chi minh',
 # Europe
 'bucharest','kraków','krakow','warsaw','warszawa','prague','gdansk','gdańsk',
 'amsterdam','eindhoven','rotterdam','heerlen','graz','zürich','zurich','geneva',
 'stockholm','solna','oslo','linkoping','linköping','madrid','barcelona','lisbon',
 'milan','munich','berlin','dublin','glasgow','knutsford','belfast','dunstable',
 'kaiseraugst','sant cugat','st. leonards','waterloo, belgium','københavn','copenhagen',
 # Middle East / Africa
 'istanbul','ankara','tel aviv','nazareth','cairo','nairobi','dubai','abu dhabi',
 # Americas (non-US)
 'toronto','vancouver','montreal','montréal','edmonton','bogota','bogotá','montevideo',
 'são paulo','sao paulo','mexico city','são leopoldo','panama','eldorado do sul',
 'belo horizonte','kanata',
 'sydney','melbourne','singapore',
 # added from jobhive eval (leaked foreign cities)
 'budapest','herzliya','brussels','hsinchu','penang','cork','sibiu','sofia',
 'tallinn','wageningen','novomoskovsk','belgrade',
}

# 2-letter / short foreign codes that DON'T collide with US state abbrevs.
# (excludes ca, in, or, etc. on purpose)
FOREIGN_CODES = {'sg','kr','cn','my','th','jp','de','fr','nl','pl','br','uk','gb',
 'au','hk','tw','se','be','cz','mx','il','ph','id','ie','ke','tr','pe','cl','ar',
 'lux','aus','ind','sgp','chn','che','pol','cze','gbr','can','deu','nld','esp','swe',
 'nor','fin','bra','jpn','kor','phl','idn','mys','tha','vnm','isr','are','sau','qat',
 'zaf','nga','egy','rou','hun','grc','ukr','rus','pak','bgd','npl','col','crc','ury',
 'pan','lka','dnk','aut','grc','bg','hu','ee'}

# Canadian-province 2-letter codes (matched only as exact comma-parts to avoid noise)
CA_PROV_CODES = {'on','qc','bc','ab','mb','sk','ns','nb','nl','pe'}

# Dominantly-US cities/tech hubs. Used only to RESCUE a multi-location string
# that pairs a foreign city with a US one ("Bangalore, San Francisco"). An
# explicit foreign COUNTRY is checked first, so "San Jose, Costa Rica" still
# drops -- these names need no country qualifier to read as US.
US_CITIES = {
 'new york','new york city','los angeles','chicago','houston','phoenix','philadelphia',
 'san antonio','san diego','dallas','san jose','austin','jacksonville','fort worth',
 'columbus','charlotte','san francisco','san francisco bay area','indianapolis','seattle',
 'denver','boston','portland','las vegas','detroit','memphis','baltimore','milwaukee',
 'albuquerque','tucson','fresno','sacramento','kansas city','atlanta','omaha','raleigh',
 'miami','long beach','oakland','minneapolis','tampa','tulsa','new orleans','cleveland',
 'nashville','pittsburgh','cincinnati','st. louis','st louis','saint louis','orlando',
 'salt lake city','durham','brooklyn','manhattan',
 # tech hubs / suburbs that show up in the data
 'cupertino','sunnyvale','santa clara','mountain view','palo alto','menlo park',
 'redwood city','san mateo','redmond','bellevue','culver city','los gatos','irvine',
 'plano','bothell','foster city','south san francisco',
}
_US_CITY_SINGLE = {c for c in US_CITIES if ' ' not in c}
_US_CITY_MULTI = {c for c in US_CITIES if ' ' in c}


def is_us_location(s: str) -> bool:
    if not s or not s.strip():
        return True
    text = s.lower().strip()
    text = re.sub(r'\b(greater|metropolitan|metro|region|remote|hybrid|onsite|on-site)\b',
                  ' ', text)
    parts = [p.strip() for p in re.split(r'[,/|;·•]+', text) if p.strip()]
    word_tokens = set()
    for p in parts:
        word_tokens.add(p)
        for w in p.split():
            word_tokens.add(w.strip('.()'))

    # 1) explicit US state / "United States" -> KEEP (always wins over foreign)
    if word_tokens & US_TOKENS or word_tokens & STATE_ABBR or word_tokens & STATE_NAME:
        return True
    if re.search(r'\b(united states|u\.?s\.?a\.?|usa)\b', text):
        return True

    # 2) explicit foreign COUNTRY -> DROP (checked before US cities so an
    #    explicit country anchors the posting: "San Jose, Costa Rica" drops)
    if word_tokens & FOREIGN_COUNTRIES:
        return False
    for name in FOREIGN_COUNTRIES:
        if ' ' in name and re.search(rf'\b{re.escape(name)}\b', text):
            return False

    # 3) known US city -> KEEP (rescues "Bangalore, San Francisco"-style lists)
    if word_tokens & _US_CITY_SINGLE:
        return True
    for name in _US_CITY_MULTI:
        if re.search(rf'\b{re.escape(name)}\b', text):
            return True

    # 4) other foreign signal (region / city / code) -> DROP
    if word_tokens & FOREIGN_REGIONS:   return False
    if word_tokens & FOREIGN_CITIES:    return False
    if word_tokens & FOREIGN_CODES:     return False
    # Canadian province code only as a standalone comma-part
    if set(parts) & CA_PROV_CODES:      return False
    # multiword foreign names (city/region) via boundary search
    for name in (FOREIGN_CITIES | FOREIGN_REGIONS):
        if ' ' in name and re.search(rf'\b{re.escape(name)}\b', text):
            return False

    # 5) ambiguous / blank / unknown -> KEEP (lenient)
    return True
