import requests, json
from bs4 import BeautifulSoup

URL = "https://jobright.ai/minisites-jobs/intern/us/ml_ai"
URL = "https://jobright.ai/minisites-jobs/intern/us/swe"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; jobpoll/1.0)"}

html = requests.get(URL, headers=HEADERS, timeout=20).text
soup = BeautifulSoup(html, "html.parser")
data = json.loads(soup.find("script", id="__NEXT_DATA__").string)

# The jobs live somewhere under props.pageProps — dump the keys to find them:
print(json.dumps(data["props"]["pageProps"], indent=2)[:2000])

# {
#       "id": "6a39d1eb1232144fb156d62f",
#       "title": "Undergraduate Technical Intern- Software and Data Solutions",
#       "company": "Pacific Northwest National Laboratory",
#       "location": "Richland,Washington,United States",
#       "salary": "$17.13-$27.02/hr",
#       "postedDate": 1782161069000,
#       "applyUrl": "https://jobright.ai/jobs/info/6a39d1eb1232144fb156d62f?utm_source=1099&utm_campaign=Software%20Engineering",
#       "workModel": "Hybrid",
#       "expLevel": null,
#       "companySize": "1001-5000",
#       "jobFunction": null,
#       "industry": [
#         "Artificial Intelligence (AI)"
#       ],
#       "qualifications": "1. Candidates must have a high school diploma /GED or higher.\n2. Candidates must be degree-seeking undergraduate students enrolled at an accredited college or university.\n3. Candidates must be taking at least 6 credit hours and have an overall cumulative GPA of 2.50.",
#       "roleType": "Inhouse",
#       "h1bSponsored": "No",
#       "isNewGrad": false,
#       "hireTime": "",
#       "graduateTime": ""
# }