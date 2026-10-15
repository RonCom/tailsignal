# Owner-field masking

33 owner columns in 7 relations; dim_pet and the other core and product tables hold none.

| Relation | Columns with a policy | TAILSIGNAL_ROLE sees clear values | TAILSIGNAL_ANALYST sees only masked values |
|---|---|---|---|
| INTERMEDIATE.INT_SOURCE_PET_PROFILES | 5 of 5 | yes | yes |
| STAGING.STG_GROOMLY__APPOINTMENTS | 4 of 4 | yes | yes |
| STAGING.STG_PAWSTAY__PETS | 5 of 5 | yes | yes |
| STAGING.STG_VET_ALPHA__VISITS | 5 of 5 | yes | yes |
| STAGING.STG_VET_BETA__ENCOUNTERS | 5 of 5 | yes | yes |
| STAGING.STG_VET_GAMMA__VISITS | 5 of 5 | yes | yes |
| STAGING.STG_WELLPLAN__MEMBERSHIPS | 4 of 4 | yes | yes |

TAILSIGNAL_ANALYST reading RAW.PAWSTAY_PETS: refused

What TAILSIGNAL_ANALYST sees in INTERMEDIATE.INT_SOURCE_PET_PROFILES:

| owner_first | owner_last | owner_email | owner_phone | owner_zip |
|---|---|---|---|---|
| *** | *** | ***@outlook.com | ***-***-6528 | 787** |
| *** | *** | ***@comcast.net | ***-***-8579 | 786** |
| *** | *** | ***@aol.com | ***-***-3937 | 190** |

**Result: PASS**
