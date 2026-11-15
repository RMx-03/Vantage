"""SEC SIC code to SPDR sector ETF table.

This map exists only to choose a sector *context symbol* for a research run, so the
run can show how a ticker's industry group has moved. It is not a classification of the
company for any advice, rating or suitability purpose, and it does not claim the ETF
describes the company's business.

The table is deterministic and incomplete on purpose. A SIC code with no sound mapping
returns ``None``, which callers must surface as a visible "missing" state. There is no
default ETF. Ranges are inclusive ``(low, high, etf)`` and must not overlap; the unit
tests check this over the whole table. Where sectors interleave, ranges are narrowed to
industry groups or single codes. Judgement calls are commented beside the range.
"""

from __future__ import annotations

SECTOR_MAP_VERSION = "sic-spdr-v1"

SECTOR_ETFS: tuple[str, ...] = (
    "XLK",
    "XLF",
    "XLV",
    "XLE",
    "XLI",
    "XLY",
    "XLP",
    "XLU",
    "XLB",
    "XLRE",
    "XLC",
)

_RANGES: tuple[tuple[int, int, str], ...] = (
    (100, 299, "XLP"),  # agricultural production: crops and livestock
    (1000, 1099, "XLB"),  # metal mining, including gold and silver
    (1200, 1399, "XLE"),  # coal, crude petroleum, natural gas and field services
    (1400, 1499, "XLB"),  # mining of nonmetallic minerals
    (1500, 1519, "XLI"),  # general building contractors
    (1520, 1531, "XLY"),  # residential builders (housing demand)
    (1532, 1799, "XLI"),  # remaining construction and special trade contractors
    (2000, 2199, "XLP"),  # food, beverages, tobacco
    (2200, 2399, "XLY"),  # textiles and apparel
    (2400, 2449, "XLB"),  # lumber and wood products (245x unmapped)
    (2500, 2599, "XLY"),  # household and office furniture
    (2600, 2669, "XLB"),  # paper and allied products
    # 2670 converted paper and paperboard products mixes packaging (materials) with
    # consumer paper: unmapped.
    (2671, 2699, "XLB"),
    (2710, 2741, "XLC"),  # newspapers, periodicals, book publishing (media)
    (2800, 2829, "XLB"),  # chemicals, plastics and resins (2821)
    (2830, 2836, "XLV"),  # medicinal chemicals, pharmaceuticals, biologicals (2834)
    (2840, 2844, "XLP"),  # soaps, cleaners, perfumes and cosmetics: household products
    (2851, 2899, "XLB"),  # paints, industrial organic chemicals, agricultural chemicals
    (2900, 2999, "XLE"),  # petroleum refining and related products
    (3080, 3089, "XLB"),  # plastics products
    (3100, 3199, "XLY"),  # leather, footwear
    (3200, 3299, "XLB"),  # stone, clay, glass, cement
    (3300, 3349, "XLB"),  # primary metals
    # 3350 rolling, drawing and extruding of nonferrous metals: mixed, unmapped.
    (3351, 3356, "XLB"),
    # 3357 drawing and insulating of nonferrous wire mixes cable makers with others.
    (3358, 3399, "XLB"),
    (3400, 3410, "XLI"),  # fabricated metal products and industrial machinery
    (3411, 3411, "XLB"),  # metal cans: packaging is Materials, not industrials
    (3412, 3532, "XLI"),
    (3533, 3533, "XLE"),  # oil and gas field machinery: energy equipment makers
    (3534, 3558, "XLI"),
    # 3559 special industry machinery mixes semiconductor equipment with other
    # machinery, so it is left unmapped.
    (3560, 3569, "XLI"),  # general industrial machinery
    (3570, 3579, "XLK"),  # computers and office equipment (3571 electronic computers)
    (3580, 3629, "XLI"),  # industrial machinery, electrical equipment
    (3630, 3639, "XLY"),  # household appliances
    (3640, 3650, "XLI"),  # electric lighting and wiring equipment
    (3651, 3651, "XLY"),  # household audio and video equipment
    (3661, 3679, "XLK"),  # comms equipment, components, chips (3674)
    (3710, 3716, "XLY"),  # motor vehicles and parts (3711); narrow, 372x is aerospace
    (3720, 3749, "XLI"),  # aircraft, ships, railroad equipment (3721)
    (3750, 3751, "XLY"),  # motorcycles and bicycles: consumer products
    (3752, 3769, "XLI"),  # trailers, missiles and space vehicles
    (3790, 3799, "XLI"),  # miscellaneous transportation equipment
    (3840, 3859, "XLV"),  # surgical, medical and dental instruments, ophthalmic goods
    (3940, 3949, "XLY"),  # toys, games, sporting and athletic goods
    (4000, 4299, "XLI"),  # railroads, transit, trucking and warehousing (4011)
    # 4400 water transportation mixes cruise lines (consumer) with shipping: unmapped.
    (4401, 4599, "XLI"),  # water and air transportation
    (4610, 4619, "XLE"),  # pipelines: energy transport, not general transport
    # 4700 transportation services mixes travel booking (consumer) with logistics.
    (4701, 4799, "XLI"),  # transportation services
    # 4810-4899 communications is a judgement call: telephone, radio, TV and cable fit the
    # Communication Services sector, so the whole 48xx group maps there (4813 telephone).
    (4810, 4899, "XLC"),
    (4900, 4921, "XLU"),  # electric services and gas production (4911)
    (4922, 4922, "XLE"),  # natural gas transmission pipelines, as with 4610-4619
    # 4923 gas transmission and distribution mixes pipelines with utilities: unmapped.
    # 4924 natural gas distribution mixes utilities with others: unmapped.
    (4925, 4949, "XLU"),  # water and combination utilities
    (4950, 4959, "XLI"),  # sanitary services and waste (industrial)
    (4960, 4999, "XLU"),  # steam, air conditioning and cogeneration supply
    (5140, 5149, "XLP"),  # groceries wholesale
    (5170, 5172, "XLE"),  # petroleum products wholesale
    # 5200 building materials and garden retail mixes home improvement (consumer) with
    # other large filers: unmapped.
    (5201, 5329, "XLY"),  # building materials retail, department stores
    (5330, 5399, "XLP"),  # variety and general merchandise stores (5331 Walmart, 5399)
    (5400, 5499, "XLP"),  # food stores
    (5500, 5699, "XLY"),  # auto dealers, gas stations, apparel retail
    (5700, 5899, "XLY"),  # home furnishings, eating and drinking places (5812)
    (5900, 5909, "XLY"),  # miscellaneous retail
    (5910, 5911, "XLP"),  # drug stores: staples, matching the SPDR staples sector
    # 5912 drug stores and proprietary stores mixes retail pharmacy with managed care
    # and distribution filers: unmapped.
    (5913, 5919, "XLP"),
    (5920, 5999, "XLY"),  # specialty and mail-order retail (5961)
    (6000, 6220, "XLF"),  # banks, credit, brokers, life and other insurance (6021)
    # 6221 commodity contracts brokers and dealers mixes exchanges, brokers and funds.
    (6222, 6323, "XLF"),  # remaining brokers, insurance (6311)
    (
        6324,
        6324,
        "XLV",
    ),  # hospital and medical service plans: managed care is Health Care
    (6325, 6499, "XLF"),  # remaining insurance carriers, agents and brokers
    (6500, 6599, "XLRE"),  # real estate operators, lessors, developers
    (6700, 6769, "XLF"),  # holding and other investment offices
    # 6770 blank checks and 6771-6797 are left unmapped: no sector is implied.
    (6798, 6798, "XLRE"),  # real estate investment trusts
    (7000, 7019, "XLY"),  # hotels and lodging
    (7310, 7319, "XLC"),  # advertising
    # 7320 consumer credit reporting and collection mixes credit bureaus (industrials
    # by GICS) with other filers: unmapped.
    (7321, 7369, "XLI"),  # credit reporting, building, rental, staffing
    # 7370 vs 7371-7379 is a judgement call. 7370 (computer services and data
    # processing, where large search and social platforms file) maps to Communication
    # Services. 7371-7379 (programming, prepackaged software, systems design,
    # processing) map to Information Technology.
    (7370, 7370, "XLC"),
    (7371, 7371, "XLK"),  # computer programming and IT services
    (7372, 7373, "XLK"),
    # 7374 computer processing and data preparation mixes payroll and data processors
    # (ADP, Verisk are industrials) with software: unmapped.
    (7375, 7379, "XLK"),
    # 7389 business services not elsewhere classified is a catch-all (payments,
    # marketplaces and more), so it is left unmapped.
    (7380, 7388, "XLI"),  # detective, security and other business services
    (7800, 7841, "XLC"),  # motion picture production and distribution (7841)
    # 7990 miscellaneous amusement and recreation mixes media and leisure: unmapped.
    (7991, 7999, "XLY"),  # amusement, gaming and recreation services
    (8000, 8099, "XLV"),  # health services, hospitals, laboratories (8062)
    (8700, 8730, "XLI"),  # engineering, accounting, management services
    # 8731 commercial physical and biological research mixes biotech with contract
    # research: unmapped.
    (8732, 8799, "XLI"),  # remaining research, management and consulting services
)


def sic_to_sector_etf(sic_code: str | None) -> str | None:
    """Return the sector context ETF for a SIC code, or ``None`` when it is not mapped.

    Accepts the string form SEC submissions give. Surrounding whitespace is stripped and
    only 3 or 4 ASCII digits are accepted. Anything else, and any unmapped code, is
    ``None``: a visible missing state, never a default ETF.
    """
    if sic_code is None:
        return None
    text = sic_code.strip()
    if not (3 <= len(text) <= 4) or not (text.isascii() and text.isdigit()):
        return None
    code = int(text)
    for low, high, etf in _RANGES:
        if low <= code <= high:
            return etf
    return None
