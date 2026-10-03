"""Build docs/business_case/DestinationPet_Data_Business_Case.xlsx: the operator business cases.

Case 2 (owned): Destination Pet owns its locations, so there are no partner data incentives. Value = internal
EBITDA uplift (Connected Care analytics) + external data revenue gated by scale.
Case 3 (blended): the owned network plus data bought from partner vet clinics, which adds the veterinary
volume drug-safety studies need. All formulas; recalc with LibreOffice after.
"""
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

OUT = Path("docs/business_case/DestinationPet_Data_Business_Case.xlsx")
F = "Arial"
BLUE, BLACK, GREEN = "0000FF", "000000", "008000"
YELLOW = PatternFill("solid", fgColor="FFFF00")
CONFIRM = PatternFill("solid", fgColor="FCE4D6")
HEAD = PatternFill("solid", fgColor="1F3A5F")
SUB = PatternFill("solid", fgColor="E8EDF3")
thin = Side(style="thin", color="B7C3D0")
USD = '$#,##0;($#,##0);"-"'
NUM = '#,##0;(#,##0);"-"'
PCT = '0.0%;(0.0%);"-"'
MULT = '0.0"x"'
YEARS = ["Year 1", "Year 2", "Year 3", "Year 4", "Year 5"]
YC = ["B", "C", "D", "E", "F"]
wb = Workbook()


def font(color=BLACK, bold=False, size=10, italic=False):
    return Font(name=F, color=color, bold=bold, size=size, italic=italic)


def header(ws, row, labels):
    for i, t in enumerate(labels):
        c = ws.cell(row=row, column=1 + i, value=t)
        c.font = Font(name=F, bold=True, color="FFFFFF", size=10)
        c.fill = HEAD
        c.alignment = Alignment(horizontal="center" if i else "left", vertical="center", wrap_text=True)


def section(ws, row, text, cols=7):
    ws.cell(row=row, column=1, value=text).font = font(bold=True, size=11)
    for j in range(1, cols + 1):
        ws.cell(row=row, column=j).fill = SUB


# ----------------------------------------------------------------------------- Read Me
rm = wb.active
rm.title = "Read Me"
rm.column_dimensions["A"].width = 115
lines = [
    ("Destination Pet: business case for a connected-care data platform", font(bold=True, size=14)),
    ("Prepared as a portfolio exercise by Chris Lavelle, from public information only. Not affiliated with or reviewed by Destination Pet.", font(italic=True, color="555555")),
    ("", font()),
    ("The question", font(bold=True, size=11)),
    ("What is a data and analytics platform worth to Destination Pet, given that it owns every location and therefore its own data?", font()),
    ("", font()),
    ("How ownership changes the case", font(bold=True, size=11)),
    ("1. No partner incentives: the largest variable cost in the partner-network version of this model disappears.", font()),
    ("2. Most value is internal: staffing, cross-selling across Connected Care services, and clinical quality, which raise EBITDA directly and therefore exit value.", font()),
    ("3. External data sales are possible but gated by scale; some products (rare drug-safety studies) need far more veterinary volume than one company has.", font()),
    ("4. New costs appear instead: unifying systems across acquired brands, and consent and privacy work.", font()),
    ("", font()),
    ("How to use", font(bold=True, size=11)),
    ("Edit blue cells on the Assumptions sheet. Peach cells are company facts to confirm with Destination Pet finance and operations. Yellow cells are the key levers.", font()),
    ("The Summary sheet shows both cases (owned; owned plus bought partner data) in three scenarios; the Model sheet shows the year-by-year build.", font()),
    ("", font()),
    ("Case 3: owned network plus partner data", font(bold=True, size=11)),
    ("Destination Pet also buys de-identified records from independent vet clinics. Partner data adds no staffing or cross-sell value (those come from operating the locations); it adds veterinary volume for drug-safety studies, wider coverage for licenses and reports, and scorecard subscriptions sold back to partners.", font()),
    ("", font()),
    ("Important", font(bold=True, size=11)),
    ("Operating inputs (labor cost, customers and patients per location, prices, the number of veterinary locations) are ILLUSTRATIVE PLACEHOLDERS. Effect sizes from TailSignal come from simulated data and carry a realization haircut. Replace inputs with company data before any decision.", font(color="C00000", bold=True)),
]
for i, (t, f) in enumerate(lines, 1):
    c = rm.cell(row=i, column=1, value=t)
    c.font = f
    c.alignment = Alignment(wrap_text=True, vertical="top")

# ----------------------------------------------------------------------------- Company Facts
cf = wb.create_sheet("Company Facts")
cf.column_dimensions["A"].width = 44
cf.column_dimensions["B"].width = 44
cf.column_dimensions["C"].width = 90
header(cf, 1, ["Fact", "Value", "Source"])
facts = [
    ("Services", "Boarding, daycare, grooming, training, veterinary care", "https://www.destinationpet.com/about-us/about/"),
    ("Operating model", "Connected Care across services; Yourgi pet app", "https://www.destinationpet.com/about-us/about/"),
    ("Locations", "190+ locations in more than 35 states (January 2024)", "https://www.stocktitan.net/news/SYF/synchrony-expands-into-pet-resorts-with-care-credit-offering-at-52p3ca1mghq4.html"),
    ("Locations page", "\"100s of locations nationwide\"; 152 listed when checked on 3 October 2026, 28 with a veterinary name (animal hospital, veterinary hospital or clinic)", "https://www.destinationpet.com/our-locations/"),
    ("Earlier count", "160+ in more than 31 states (June 2023)", "https://www.prnewswire.com/news-releases/destination-pet-strengthens-position-in-the-pet-care-industry-with-pet-palace-acquisition-301856956.html"),
    ("VitalPet acquisition", "24 veterinary hospitals in seven states (March 2020)", "https://www.prnewswire.com/news-releases/destination-pet-to-acquire-vitalpet-301024514.html"),
    ("Acquisition example", "Pet Palace: 11 facilities, 500+ employees (June 2023)", "Same press release"),
    ("Owner", "LetterOne (acquired November 2019)", "https://www.cbinsights.com/company/destination-pet"),
    ("2025 performance", "Return to full-year profitability; revenue ahead of plan; M&A accretive", "https://letterone.com/news-and-insights/2025-year-in-review-l1-health/"),
    ("Yourgi app", "Gross booking value growing >100% a year; became a two-sided marketplace in November 2025", "Same LetterOne review"),
    ("Not public (confirm)", "Number of veterinary locations, revenue and labor cost per location, active pets", "Inputs on the Assumptions sheet are placeholders"),
]
for i, (a_, b_, c_) in enumerate(facts, 2):
    for j, v in enumerate((a_, b_, c_)):
        c = cf.cell(row=i, column=1 + j, value=v)
        c.font = font(italic=(j == 2), color="555555" if j == 2 else BLACK, bold=(j == 0))
        c.alignment = Alignment(wrap_text=True, vertical="top")

# ----------------------------------------------------------------------------- Assumptions
a = wb.create_sheet("Assumptions")
a.column_dimensions["A"].width = 58
for col in YC:
    a.column_dimensions[col].width = 13
a.column_dimensions["G"].width = 78
A = {}


def inp(row, label, value, fmt, name, note=None, fill=None):
    a.cell(row=row, column=1, value=label).font = font()
    c = a.cell(row=row, column=2, value=value)
    c.font = font(BLUE)
    c.number_format = fmt
    if fill is not None:
        c.fill = fill
    if note:
        n = a.cell(row=row, column=7, value=note)
        n.font = font(italic=True, color="555555")
        n.alignment = Alignment(wrap_text=True)
    A[name] = f"Assumptions!$B${row}"


def inp_years(row, label, values, fmt, name, note=None, fill=None):
    a.cell(row=row, column=1, value=label).font = font()
    for j, v in enumerate(values):
        c = a.cell(row=row, column=2 + j, value=v)
        c.font = font(BLUE)
        c.number_format = fmt
        if fill is not None:
            c.fill = fill
    if note:
        n = a.cell(row=row, column=7, value=note)
        n.font = font(italic=True, color="555555")
        n.alignment = Alignment(wrap_text=True)
    A[name] = row


a.cell(row=1, column=1, value="Assumptions").font = font(bold=True, size=14)
a.cell(row=2, column=1, value="Blue = input · peach fill = company fact to confirm · yellow fill = key lever").font = font(italic=True, color="555555")
r = 4
section(a, r, "Scenarios")
r += 1
header(a, r, ["Scenario", "Value effects ×", "External prices ×", "", "", "", "Note"])
scen = [("Low", 0.5, 0.8), ("Base", 1.0, 1.0), ("High", 1.4, 1.15)]
A["scen"] = []
for nm, v1, v2 in scen:
    r += 1
    a.cell(row=r, column=1, value=nm).font = font(bold=True)
    for j, v in enumerate((v1, v2)):
        c = a.cell(row=r, column=2 + j, value=v)
        c.font = font(BLUE)
        c.number_format = '0.00"x"'
        c.fill = YELLOW
    A["scen"].append(r)
a.cell(row=A["scen"][0], column=7, value="Value effects scale every internal benefit; prices scale every external sale").font = font(italic=True, color="555555")

r += 2
section(a, r, "Network (company facts to confirm)")
r += 1
inp(r, "Locations (all service types)", 190, NUM, "locations", "Public: 190+ in 35+ states (January 2024); the website says \"100s\" and lists 152", CONFIRM)
r += 1
inp(r, "Locations with a veterinary clinic", 30, NUM, "vet_locations",
    "Not public: 28 listed locations carry a veterinary name; VitalPet brought 24 hospitals in 2020", CONFIRM)
r += 1
inp(r, "Unique pets served per location per year", 3000, NUM, "pets_per_loc", "Not public; placeholder", CONFIRM)
r += 1
inp(r, "Dogs with veterinary records per vet clinic per year", 3500, NUM, "dogs_per_clinic", "Not public; placeholder", CONFIRM)
r += 1
inp(r, "Daycare and boarding labor cost per location ($ per year)", 700000, USD, "labor", "Not public; placeholder", CONFIRM)
r += 1
inp(r, "Share of resort customers not using a company vet", 0.80, PCT, "nonvet_share", "Not public; placeholder", CONFIRM)

r += 2
section(a, r, "Rollout")
r += 1
header(a, r, ["Item"] + YEARS + ["Note"])
r += 1
inp_years(r, "Share of locations live on the platform", [0.15, 0.50, 0.85, 1.0, 1.0], PCT, "live",
          "Systems from acquired brands unified over two to three years", YELLOW)

r += 2
section(a, r, "Internal value drivers (effects from TailSignal, with a realization haircut)")
r += 1
header(a, r, ["Driver", "Value", "", "", "", "", "Evidence"])
r += 1
inp(r, "Daycare staffing cost reduction from demand forecasting", 0.07, PCT, "staff_effect",
    "TailSignal backtest, simulated data: 7% lower staffing cost than the seasonal baseline (docs/analytics_results.md)")
r += 1
inp(r, "Realization of simulated effects in practice", 0.50, PCT, "realize", "Haircut for moving from simulation to operations", YELLOW)
r += 1
inp(r, "Extra conversion of resort customers to company vet care (points)", 0.01, PCT, "xsell_pts",
    "Assumption: targeted Connected Care offers from daycare, boarding and grooming records", YELLOW)
r += 1
inp(r, "Annual veterinary revenue per new client ($)", 600, USD, "vet_rev_client", "Placeholder", CONFIRM)
r += 1
inp(r, "Contribution margin on added veterinary revenue", 0.40, PCT, "vet_margin", "Placeholder", CONFIRM)
r += 1
inp(r, "Extra dental cleanings per vet clinic per year from better charting", 40, NUM, "dental_extra",
    "TailSignal: under-charting clinics record 35-43% less dental disease; bring them to the median")
r += 1
inp(r, "Average dental cleaning price ($)", 700, USD, "dental_price", "Placeholder", CONFIRM)
r += 1
inp(r, "Contribution margin on dental cleanings", 0.45, PCT, "dental_margin", "Placeholder", CONFIRM)
r += 1
inp(r, "Membership retention benefit per location ($ per year)", 0, USD, "retention",
    "TailSignal reminder-targeting pilot was inconclusive; set to zero until a larger pilot proves it")

r += 2
section(a, r, "External data revenue (illustrative prices)")
r += 1
header(a, r, ["Item", "Value", "", "", "", "", "Basis"])
r += 1
inp(r, "Data-license annual contract value ($)", 120000, USD, "lic_acv", "De-identified cohort, Pet Health Index, service benchmarks")
r += 1
inp(r, "Pets observed per year needed before licensing", 100000, NUM, "lic_gate",
    "Privacy: 8% of pets suppressed at ~12,700 pets; assume ~8x that for clean releases")
r += 1
inp(r, "Research report average price ($)", 40000, USD, "rep_price", "Pet food, dental-care and drug makers")
r += 1
inp(r, "Signal-validation study price ($ per study)", 250000, USD, "study_price", "Drug-safety study for a manufacturer")
r += 1
inp(r, "Dog records needed for common side-effect studies (4-year window)", 792000, NUM, "gate_common",
    "TailSignal Model A2: ~80x a 9,900-dog network")
r += 1
inp(r, "Dog records needed for rare side-effect studies (4-year window)", 1287000, NUM, "gate_rare",
    "TailSignal Model A2: ~130x a 9,900-dog network")
r += 1
inp(r, "Study delivery cost (% of study revenue)", 0.40, PCT, "study_cogs", "Clinical review and annotation")
r += 2
header(a, r, ["Volume by year"] + YEARS + ["Note"])
r += 1
inp_years(r, "Data licensees", [0, 2, 3, 5, 6], NUM, "licensees", "Sold only once the license gate is met")
r += 1
inp_years(r, "Research reports sold", [1, 3, 4, 5, 6], NUM, "reports")
r += 1
inp_years(r, "Common side-effect studies (if gate met)", [0, 0, 1, 2, 2], NUM, "studies_common")
r += 1
inp_years(r, "Rare side-effect studies (if gate met)", [0, 0, 0, 1, 1], NUM, "studies_rare")

r += 2
section(a, r, "Case 3: partner data bought from independent vet clinics")
r += 1
header(a, r, ["Item", "Value", "", "", "", "", "Basis"])
r += 1
inp(r, "Data fee paid per partner clinic ($ per year)", 1000, USD, "p_fee", "Same incentive as the partner-network case", YELLOW)
r += 1
inp(r, "Onboarding cost per new partner clinic (one-time, $)", 2000, USD, "p_onboard", "Data-feed mapping and contract")
r += 1
inp(r, "Dogs with veterinary records per partner clinic per year", 3500, NUM, "p_dogs", "Same placeholder as company clinics")
r += 1
inp(r, "Pets observed per partner clinic per year", 3000, NUM, "p_pets", "Placeholder")
r += 1
inp(r, "Partner clinics buying the premium scorecard", 0.40, PCT, "p_uptake", "Partner-network case assumption")
r += 1
inp(r, "Premium scorecard price ($ per clinic per year)", 1800, USD, "p_premium", "Partner-network case price")
r += 2
header(a, r, ["Case 3 volume by year"] + YEARS + ["Note"])
r += 1
inp_years(r, "Partner vet clinics supplying data", [0, 40, 80, 100, 100], NUM, "partners",
          "About 60 partner clinics on top of 30 company clinics clear the rare-study gate over four years", YELLOW)
r += 1
inp_years(r, "Added data-team headcount (partner data)", [0, 1, 1, 2, 2], NUM, "p_head", "Partner management and data engineering")
r += 1
inp_years(r, "Data licensees (Case 3)", [0, 2, 4, 5, 7], NUM, "licensees3", "Wider veterinary coverage")
r += 1
inp_years(r, "Research reports sold (Case 3)", [1, 3, 5, 6, 7], NUM, "reports3")
r += 1
inp_years(r, "Common side-effect studies (Case 3, if gate met)", [0, 0, 1, 2, 3], NUM, "studies_common3")
r += 1
inp_years(r, "Rare side-effect studies (Case 3, if gate met)", [0, 0, 0, 1, 2], NUM, "studies_rare3")

r += 2
section(a, r, "Costs")
r += 1
header(a, r, ["Item", "Value", "", "", "", "", "Basis"])
r += 1
inp(r, "Loaded cost per data-team employee ($ per year)", 200000, USD, "loaded", "Placeholder")
r += 1
inp(r, "System integration cost per location (one-time, $)", 15000, USD, "integration",
    "Unify practice-management and booking systems from acquired brands", YELLOW)
r += 1
inp(r, "Cloud and tooling, fixed ($ per year)", 150000, USD, "infra_fixed", "Placeholder")
r += 1
inp(r, "Cloud and tooling per live location ($ per year)", 600, USD, "infra_loc", "Placeholder")
r += 1
inp(r, "Privacy, consent and legal ($ per year)", 150000, USD, "privacy", "Customer consent for de-identified use; data-sale contracts")
r += 2
header(a, r, ["Headcount by year"] + YEARS + ["Note"])
r += 1
inp_years(r, "Data team headcount", [5, 8, 10, 11, 12], NUM, "headcount", "Data science, data engineering, analytics product, privacy", YELLOW)

r += 2
section(a, r, "Valuation")
r += 1
inp(r, "EV / EBITDA exit multiple applied to run-rate uplift", 12.0, MULT, "multiple",
    "Placeholder for a PE-owned multi-site pet services business; confirm with the deal team", YELLOW)

# ----------------------------------------------------------------------------- Model
m = wb.create_sheet("Model")
m.column_dimensions["A"].width = 58
for col in YC:
    m.column_dimensions[col].width = 15
m.cell(row=1, column=1, value="Five-year build by case and scenario ($)").font = font(bold=True, size=14)
m.cell(row=2, column=1, value="All cells are formulas driven by the Assumptions sheet.").font = font(italic=True, color="555555")
AY = YC
blocks = {}
CASES = [("Owned", "Case 2: owned network"), ("Blended", "Case 3: owned network + partner data")]
r = 4
for case, case_title in CASES:
    blended = case == "Blended"
    for si, (nm, _, _) in enumerate(scen):
        sr = A["scen"][si]
        vx, px = f"Assumptions!$B${sr}", f"Assumptions!$C${sr}"
        section(m, r, f"{case_title}, {nm} scenario", 6)
        r += 1
        header(m, r, ["Line"] + YEARS)
        r += 1
        rows = {}

        def line(label, formulas, fmt=USD, bold=False, name=None):
            global r
            m.cell(row=r, column=1, value=label).font = font(bold=bold)
            for j, f in enumerate(formulas):
                c = m.cell(row=r, column=2 + j, value=f)
                c.number_format = fmt
                c.font = font(bold=bold)
                if bold:
                    c.border = Border(top=thin)
            if name:
                rows[name] = r
            r += 1

        yv = lambda key, j: f"Assumptions!{AY[j]}${A[key]}"
        live = lambda j: yv("live", j)
        zero = ["=0"] * 5
        line("Live locations", [f"=ROUND({A['locations']}*{live(j)},0)" for j in range(5)], NUM, name="live_loc")
        line("Live vet clinics", [f"=ROUND({A['vet_locations']}*{live(j)},0)" for j in range(5)], NUM, name="live_vet")
        line("Live resort locations (daycare, boarding, grooming)",
             [f"=ROUND(({A['locations']}-{A['vet_locations']})*{live(j)},0)" for j in range(5)], NUM, name="live_res")
        line("Partner vet clinics supplying data", [f"={yv('partners', j)}" for j in range(5)] if blended else zero, NUM,
             name="partners")
        ll = lambda j: f"{YC[j]}{rows['live_loc']}"
        lv = lambda j: f"{YC[j]}{rows['live_vet']}"
        lr = lambda j: f"{YC[j]}{rows['live_res']}"
        lp = lambda j: f"{YC[j]}{rows['partners']}"
        line("Pets observed per year", [f"={ll(j)}*{A['pets_per_loc']}+{lp(j)}*{A['p_pets']}" for j in range(5)], NUM,
             name="pets")
        line("Dog veterinary records per year", [f"={lv(j)}*{A['dogs_per_clinic']}+{lp(j)}*{A['p_dogs']}" for j in range(5)],
             NUM, name="dog_year")
        line("Dog veterinary records, trailing 4 years (study window)",
             [f"=SUM({YC[max(0, j - 3)]}{rows['dog_year']}:{YC[j]}{rows['dog_year']})" for j in range(5)], NUM,
             name="dog_records")
        # internal value: staffing and cross-sell come from resort locations; dental from vet clinics
        line("Internal: daycare and boarding staffing savings",
             [f"={lr(j)}*{A['labor']}*{A['staff_effect']}*{A['realize']}*{vx}" for j in range(5)], name="v_staff")
        line("Internal: Connected Care cross-sell to vet (contribution)",
             [f"={lr(j)}*{A['pets_per_loc']}*{A['nonvet_share']}*{A['xsell_pts']}*{A['vet_rev_client']}*{A['vet_margin']}*{A['realize']}*{vx}"
              for j in range(5)], name="v_xsell")
        line("Internal: dental capture (contribution)",
             [f"={lv(j)}*{A['dental_extra']}*{A['dental_price']}*{A['dental_margin']}*{A['realize']}*{vx}" for j in range(5)],
             name="v_dental")
        line("Internal: membership retention", [f"={ll(j)}*{A['retention']}*{vx}" for j in range(5)], name="v_ret")
        line("Internal value (EBITDA)", [f"=SUM({YC[j]}{rows['v_staff']}:{YC[j]}{rows['v_ret']})" for j in range(5)],
             bold=True, name="v_int")
        lic, rep, sc_, sr_ = (("licensees3", "reports3", "studies_common3", "studies_rare3") if blended
                              else ("licensees", "reports", "studies_common", "studies_rare"))
        line("External: data licenses",
             [f"=IF({YC[j]}{rows['pets']}>={A['lic_gate']},{yv(lic, j)}*{A['lic_acv']}*{px},0)" for j in range(5)],
             name="x_lic")
        line("External: research reports", [f"={yv(rep, j)}*{A['rep_price']}*{px}" for j in range(5)], name="x_rep")
        line("External: common side-effect studies",
             [f"=IF({YC[j]}{rows['dog_records']}>={A['gate_common']},{yv(sc_, j)}*{A['study_price']}*{px},0)"
              for j in range(5)], name="x_sc")
        line("External: rare side-effect studies",
             [f"=IF({YC[j]}{rows['dog_records']}>={A['gate_rare']},{yv(sr_, j)}*{A['study_price']}*{px},0)"
              for j in range(5)], name="x_sr")
        line("External: premium scorecards sold to partner clinics",
             [f"={lp(j)}*{A['p_uptake']}*{A['p_premium']}*{px}" for j in range(5)], name="x_prem")
        line("External revenue", [f"=SUM({YC[j]}{rows['x_lic']}:{YC[j]}{rows['x_prem']})" for j in range(5)], bold=True,
             name="x_rev")
        # costs
        head = (lambda j: f"({yv('headcount', j)}+{yv('p_head', j)})") if blended else (lambda j: yv("headcount", j))
        line("Data team", [f"={head(j)}*{A['loaded']}" for j in range(5)], name="c_team")
        line("System integration (one-time, newly live locations)",
             [f"={ll(0)}*{A['integration']}"] + [f"=MAX(0,{ll(j)}-{ll(j - 1)})*{A['integration']}" for j in range(1, 5)],
             name="c_int")
        line("Cloud and tooling", [f"={A['infra_fixed']}+({ll(j)}+{lp(j)})*{A['infra_loc']}" for j in range(5)], name="c_infra")
        line("Privacy, consent and legal", [f"={A['privacy']}" for j in range(5)], name="c_priv")
        line("Study delivery", [f"=({YC[j]}{rows['x_sc']}+{YC[j]}{rows['x_sr']})*{A['study_cogs']}" for j in range(5)],
             name="c_study")
        line("Partner data fees", [f"={lp(j)}*{A['p_fee']}" for j in range(5)], name="c_pfee")
        line("Partner onboarding (one-time, new partners)",
             [f"={lp(0)}*{A['p_onboard']}"] + [f"=MAX(0,{lp(j)}-{lp(j - 1)})*{A['p_onboard']}" for j in range(1, 5)],
             name="c_pon")
        line("Total platform cost", [f"=SUM({YC[j]}{rows['c_team']}:{YC[j]}{rows['c_pon']})" for j in range(5)],
             bold=True, name="cost")
        line("Net EBITDA impact", [f"={YC[j]}{rows['v_int']}+{YC[j]}{rows['x_rev']}-{YC[j]}{rows['cost']}" for j in range(5)],
             bold=True, name="net")
        line("Cumulative net impact", [f"={YC[0]}{rows['net']}"] + [f"={YC[j - 1]}{r}+{YC[j]}{rows['net']}" for j in range(1, 5)],
             name="cum")
        line("Helper: year number if cumulative impact positive (else 99)",
             [f"=IF({YC[j]}{rows['cum']}>0,{j + 1},99)" for j in range(5)], NUM, name="pay")
        blocks[(case, nm)] = rows
        r += 1

# ----------------------------------------------------------------------------- Summary
s = wb.create_sheet("Summary", 1)
s.column_dimensions["A"].width = 56
for col in "BCD":
    s.column_dimensions[col].width = 18
s.cell(row=1, column=1, value="Summary by case and scenario").font = font(bold=True, size=14)
s.cell(row=2, column=1, value="Placeholders drive these results; see Read Me.").font = font(italic=True, color="C00000")
meas = [("Internal value, Year 5 (EBITDA)", "v_int", USD), ("External data revenue, Year 5", "x_rev", USD),
        ("Platform cost, Year 5", "cost", USD), ("Net EBITDA impact, Year 5", "net", USD),
        ("Cumulative net impact, Years 1-5", "cum", USD)]
row = 4
for case, case_title in CASES:
    header(s, row, [case_title, "Low", "Base", "High"])
    row += 1
    for lbl, key, fmt in meas:
        s.cell(row=row, column=1, value=lbl).font = font()
        for j, nm in enumerate(["Low", "Base", "High"]):
            c = s.cell(row=row, column=2 + j, value=f"=Model!F{blocks[(case, nm)][key]}")
            c.font = font(GREEN)
            c.number_format = fmt
        row += 1
    s.cell(row=row, column=1, value="Enterprise value from Year-5 net impact (x exit multiple)").font = font(bold=True)
    for j, nm in enumerate(["Low", "Base", "High"]):
        c = s.cell(row=row, column=2 + j, value=f"=MAX(0,Model!F{blocks[(case, nm)]['net']})*{A['multiple']}")
        c.number_format = USD
        c.font = font(bold=True)
    row += 1
    s.cell(row=row, column=1, value="Payback year (cumulative impact turns positive)").font = font()
    for j, nm in enumerate(["Low", "Base", "High"]):
        b = blocks[(case, nm)]["pay"]
        c = s.cell(row=row, column=2 + j, value=f'=IF(MIN(Model!B{b}:F{b})=99,"Not within 5 years","Year "&MIN(Model!B{b}:F{b}))')
        c.alignment = Alignment(horizontal="right")
        c.font = font()
    row += 2
header(s, row, ["Where Year-5 value comes from (Base)", "Case 2 ($)", "Case 3 ($)"])
mix = [("Staffing savings", "v_staff"), ("Connected Care cross-sell", "v_xsell"), ("Dental capture", "v_dental"),
       ("Membership retention", "v_ret"), ("Data licenses", "x_lic"), ("Research reports", "x_rep"),
       ("Common side-effect studies", "x_sc"), ("Rare side-effect studies", "x_sr"),
       ("Premium scorecards sold to partners", "x_prem"), ("Partner data fees and onboarding (cost)", None)]
for lbl, key in mix:
    row += 1
    s.cell(row=row, column=1, value=lbl).font = font()
    for j, case in enumerate(["Owned", "Blended"]):
        b = blocks[(case, "Base")]
        f = f"=Model!F{b[key]}" if key else f"=-(Model!F{b['c_pfee']}+Model!F{b['c_pon']})"
        c = s.cell(row=row, column=2 + j, value=f)
        c.font = font(GREEN)
        c.number_format = USD

# ----------------------------------------------------------------------------- Scale Gates
g = wb.create_sheet("Scale Gates", 2)
g.column_dimensions["A"].width = 46
g.column_dimensions["B"].width = 16
for col in "CDEF":
    g.column_dimensions[col].width = 16
g.column_dimensions["G"].width = 60
g.cell(row=1, column=1, value="What the owned network unlocks alone, and with partner data").font = font(bold=True, size=14)
header(g, 3, ["Capability", "Needs", "Case 2: year reached", "Case 2: Year 5", "Case 3: year reached", "Case 3: Year 5",
              "Implication"])
gates = [("Data licenses (pets observed per year)", "lic_gate", "pets",
          "Reached early: owning every channel gives volume quickly"),
         ("Common side-effect studies (dog records, 4 yrs)", "gate_common", "dog_records",
          "Depends on veterinary volume, not resort volume"),
         ("Rare side-effect studies (dog records, 4 yrs)", "gate_rare", "dog_records",
          "Out of reach for the owned network alone; partner data closes the gap")]
for i, (lbl, need, metric, imp) in enumerate(gates):
    q = 4 + i
    g.cell(row=q, column=1, value=lbl).font = font()
    c = g.cell(row=q, column=2, value=f"={A[need]}")
    c.font = font(GREEN)
    c.number_format = NUM
    for k, case in enumerate(["Owned", "Blended"]):
        rr = blocks[(case, "Base")][metric]
        f = ("=IF(Model!B{r}>=$B{q},\"Year 1\",IF(Model!C{r}>=$B{q},\"Year 2\",IF(Model!D{r}>=$B{q},\"Year 3\","
             "IF(Model!E{r}>=$B{q},\"Year 4\",IF(Model!F{r}>=$B{q},\"Year 5\",\"Not in 5 years\")))))").format(r=rr, q=q)
        c = g.cell(row=q, column=3 + 2 * k, value=f)
        c.font = font()
        c.alignment = Alignment(horizontal="center")
        c = g.cell(row=q, column=4 + 2 * k, value=f"=Model!F{rr}")
        c.font = font(GREEN)
        c.number_format = NUM
    g.cell(row=q, column=7, value=imp).font = font(italic=True, color="555555")

for ws in wb.worksheets:
    ws.sheet_view.showGridLines = False
OUT.parent.mkdir(parents=True, exist_ok=True)
wb.save(OUT)
print(OUT)
