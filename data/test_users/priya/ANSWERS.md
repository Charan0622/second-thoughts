# Test user: Priya Nair (fictional)

Comfortable: about $2,158 free before payday. Owns a Kindle, a Garmin watch and a Dyson, and is saving for a car.

## Upload (📄 Use my documents)
- **Bank statement:** `bank_statement.pdf`. Expect balance $4,920.00, 4 upcoming bills, free cash ≈ **$2,158.01**.
- **Pay stub:** `pay_stub.jpg`. Expect next payday 2026-11-27.
- **Receipts:** add the files in `receipts/` one at a time, and check that the owned list grows.

## Quick questions: type these
| Question | Answer |
|---|---|
| What are you saving for? | Car down payment |
| By when? | March 2027 |
| Target amount ($) | 8000 |
| Saved so far ($) | 5200 |
| Saving per month ($) | 400 (the panel should suggest about this from the statement's savings transfer) |
| Rules | No single purchase over $500 without waiting 48 hours / Fitness gear is fine |

## Things to try (photos in `data/test_users/products/`)
- `tag_switch2.jpg` ($449.99)
- `tag_kindle_scribe.jpg` ($399.99)
- `tag_yeti_bottle.jpg` ($40)
- `tag_belvita.jpg` ($3.49)
- `tag_lululemon.jpg` ($98)
- `notag_airpods_pro.jpg`: no price shown, so the app should look the price up online and ask you to confirm.
