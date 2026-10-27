# BizCrax36 — Public Opportunity Source Register (2026-10-27)

These are verified public source routes, **not** a verified feed of current open awards. Recheck the original issuer before any action.

| Type | Source | URL | Access limitation |
|---|---|---|---|
| Federal tenders | MyProcurement | https://myprocurement.treasury.gov.my/advertisements/tender | Portal warns publication may lag; cross-check ePerolehan |
| Federal supplier system | ePerolehan | https://www.eperolehan.gov.my/ | Registration and qualification may be required |
| Central bank procurement | BNM | https://www.bnm.gov.my/procurement | Public notices; detailed requirements for approved suppliers |
| Energy supply chain | PETRONAS | https://www.petronas.com/suppliers/licensing-procurement-malaysia | Licensing, registration and category qualifications required |
| Capital-market regulator procurement | SC | https://www.sc.com.my/resources/sc-procurement | E-procurement vendor registration required |
| Telecom supplier opportunities | Telekom Malaysia | https://www.tm.com.my/registration | Supplier onboarding required |
| Industry investment signals | MIDA | https://www.mida.gov.my/ | Investment approvals are not open tenders |
| SME financing | BNM | https://www.bnm.gov.my/sme-financing | Applications subject to bank credit assessment |
| International tenders | UNGM | https://www.ungm.org/Public/notice | Issuer-specific eligibility and deadlines |
| International projects | World Bank | https://projects.worldbank.org/en/projects-operations/opportunities | Upcoming projects not equivalent to awarded contracts |
| EU tenders | TED | https://ted.europa.eu/ | Country-specific eligibility and documentation |

## Additional opportunity classes
- Personal/microbusiness: direct customer demand, digital services, repairs, consulting, product development; evidence must be obtained from actual customers, public data or authorized listings.
- Private RFQs and supplier onboarding: capture exact issuing entity and published requirements.
- Business collaboration: vendor development, licensing, distribution, joint ventures, subcontracting.
- Investments and acquisitions: authorized offering evidence, legal ownership and independent financial diligence; no speculative sale listings.

## Provenance rules
1. Each claimed live notice must have issuer, title, source URL, observed timestamp, published date, closing date (if applicable), eligibility, value with currency (or null), and immutable evidence fingerprint.
2. Distinguish SOURCE_RETRIEVED, NOTICE_EXTRACTED, ISSUER_VERIFIED, OPEN_RECHECKED, ELIGIBILITY_REVIEWED and INVESTMENT_READY. Never skip gates.
3. Mark stale, unavailable, restricted or unverified results prominently. A portal homepage is not proof of an individual live tender.
4. Financing and investment forecasts must show assumptions, downside/base/upside scenarios, cash-flow timing and citations.
5. Respect website terms, robots restrictions, authentication and rate limits. Do not bypass restricted content.

## Next implementation milestones
Scheduled source checks; source-specific parsers; schema validation; evidence snapshots; duplicate detection; deadline recheck; company verification; financial and technical report generation; audited browser-based end-to-end tests.
