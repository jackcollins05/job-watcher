"""Approved source plan, transcribed from local successful audit evidence.

No fetching and no import-time file/network access.
JPMorgan Chase MUST use analyst (7,008 -> 1,003 in the approved audit).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    key: str
    employer: str
    platform: str
    endpoint: str | None
    method: str | None
    search_term: str = ""
    notes: str = ""
    site_number: str = ""
    capped_total_risk: bool = False


PRIMARY_SOURCES = (
    Source('tyson_foods', 'Tyson Foods', 'Workday CXS', 'https://tysonfoods.wd5.myworkdayjobs.com/wday/cxs/tysonfoods/TSN/jobs', 'POST', '', ''),
    Source('walmart', 'Walmart', 'Workday CXS', 'https://walmart.wd504.myworkdayjobs.com/wday/cxs/walmart/WalmartExternal/jobs', 'POST', '', 'Observed total 2000 may be capped.', capped_total_risk=True),
    Source('pepsico', 'PepsiCo', 'iCIMS / Jibe', 'https://www.pepsicojobs.com/api/jobs', 'GET', '', 'Tested lang=en-us, limit=2, page=1. Next page and language scope unresolved.'),
    Source('jb_hunt', 'J.B. Hunt', 'Workday CXS', 'https://jbhunt.wd501.myworkdayjobs.com/wday/cxs/jbhunt/Careers/jobs', 'POST', '', ''),
    Source('simmons_bank', 'Simmons Bank', 'Workday CXS', 'https://simmonsbank.wd5.myworkdayjobs.com/wday/cxs/simmonsbank/SimmonsCareers/jobs', 'POST', '', ''),
    Source('bank_of_america', 'Bank of America', 'Workday CXS', 'https://ghr.wd1.myworkdayjobs.com/wday/cxs/ghr/Lateral-US/jobs', 'POST', '', ''),
    Source('jpmorgan_chase', 'JPMorgan Chase', 'Oracle Recruiting CE', 'https://jpmc.fa.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions', 'GET', 'analyst', 'Public site CX_1001; finder findReqs with keyword=analyst. README must disclose search term.', site_number='CX_1001'),
    Source('wells_fargo', 'Wells Fargo', 'Workday CXS', 'https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/WellsFargoJobs/jobs', 'POST', '', ''),
    Source('citi', 'Citi', 'Workday CXS', 'https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs', 'POST', '', 'Observed total 2000 may be capped.', capped_total_risk=True),
    Source('truist', 'Truist', 'Workday CXS', 'https://truist.wd1.myworkdayjobs.com/wday/cxs/truist/Careers/jobs', 'POST', '', ''),
    Source('pnc', 'PNC', 'Workday CXS', 'https://pnc.wd5.myworkdayjobs.com/wday/cxs/pnc/External/jobs', 'POST', '', ''),
    Source('us_bank', 'U.S. Bank', 'Workday CXS', 'https://usbank.wd1.myworkdayjobs.com/wday/cxs/usbank/US_Bank_Careers/jobs', 'POST', '', ''),
    Source('capital_one', 'Capital One', 'Workday CXS', 'https://capitalone.wd12.myworkdayjobs.com/wday/cxs/capitalone/Capital_One/jobs', 'POST', '', ''),
    Source('fifth_third_bank', 'Fifth Third Bank', 'Workday CXS', 'https://fifththird.wd5.myworkdayjobs.com/wday/cxs/fifththird/53careers/jobs', 'POST', '', ''),
    Source('bmo', 'BMO', 'Workday CXS', 'https://bmo.wd3.myworkdayjobs.com/wday/cxs/bmo/External/jobs', 'POST', '', ''),
)

BACKUP_SOURCES = (
    Source('huntington_bank', 'Huntington Bank', 'Workday CXS', 'https://huntington.wd12.myworkdayjobs.com/wday/cxs/huntington/HNBcareers/jobs', 'POST', '', ''),
    Source('keybank', 'KeyBank', 'Workday CXS', 'https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/External_Career_Site/jobs', 'POST', '', ''),
)

DROPPED_SOURCES = (
    Source("regions_bank", "Regions Bank", "Workday CXS", 'https://regions.wd5.myworkdayjobs.com/wday/cxs/regions/Regions/jobs', "POST", notes="Current endpoint returned HTTP 404."),
    Source("nestle", "Nestlé", "Unvalidated", None, None, notes="No validated anonymous JSON endpoint."),
    Source("arvest_bank", "Arvest Bank", "Unvalidated", None, None, notes="No validated anonymous JSON endpoint."),
)
