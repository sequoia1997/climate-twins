"""World regions by ISO 3166-1 alpha-2 code. Used to group world places into download shards (export.py) and to
give extra coverage to under-sampled regions when the place list is expanded (expand.py). Unknown codes fall
into "Other", so a new country never breaks a build."""
from __future__ import annotations

_R = {
    "Africa": "DZ AO BJ BW BF BI CM CV CF TD KM CG CD CI DJ EG GQ ER SZ ET GA GM GH GN GW KE LS LR LY MG MW ML MR MU "
              "MA MZ NA NE NG RW ST SN SC SL SO ZA SS SD TZ TG TN UG ZM ZW EH RE YT SH",
    "Middle East": "AE BH IR IQ IL JO KW LB OM PS QA SA SY TR YE CY",
    "Central Asia": "AF KZ KG TJ TM UZ AM AZ GE",
    "South Asia": "IN PK BD LK NP BT MV",
    "East Asia": "CN JP KP KR TW HK MO MN",
    "Southeast Asia": "BN KH ID LA MY MM PH SG TH TL VN",
    "Europe": "AL AD AT BY BE BA BG HR CZ DK EE FI FR DE GR HU IS IE IT XK LV LI LT LU MT MD MC ME NL MK NO PL PT RO "
              "RU SM RS SK SI ES SE CH UA GB VA FO AX IM GG JE GI",
    "Latin America": "AR BZ BO BR CL CO CR CU DO EC SV GT GY HT HN JM NI PA PY PE SR TT UY VE AG BB BS DM GD KN LC VC "
                     "PR GF CW VI TC MS FK AW AI BM KY VG GP MQ BL MF SX BQ",
    "Oceania": "AU NZ PG FJ SB VU WS TO KI TV FM MH PW NR NC PF MP GU AS CK NU TK WF",
    "North America": "US CA MX GL PM",
}
REGION = {c: r for r, cs in _R.items() for c in cs.split()}

# regions that get denser coverage when the world list is expanded (fewest places per million km2 and per person)
PRIORITY = {"Africa", "Latin America", "Central Asia", "Oceania", "Middle East"}


def region(iso: str, lat: float | None = None) -> str:
    """Region of a country code. Hawaii (US) is grouped with Oceania by latitude/longitude when they are given."""
    if iso == "US" and lat is not None and lat < 23:
        return "Oceania"
    return REGION.get(iso, "Other")
