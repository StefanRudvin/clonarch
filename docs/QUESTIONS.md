# Owner answers and remaining questions

## Confirmed by owner (2026-10-27)

1. **Host:** this VM; owner wants the web server started here and permits choosing a listening port. Keep the original LAN-only/no-public-exposure constraint. Observed private IP `192.168.105.10`; proposed unused port 8787. No firewall/router/startup changes implicitly approved.
2. **Plaid:** owner will use the Trial plan and provide authorization later. Current official billing docs confirm a free Trial with 10 lifetime Production Items; dashboard entitlement still needs confirmation. See INTEGRATIONS.md.
3. **Cards:** four distinct cards. Latest stated inventory is **two Chase cards/accounts and two Amex cards/accounts**, superseding original three Chase/one Amex. Exact ownership and shared-login grouping can be selected during Link; owner checking is additional.
4. **Reporting:** USD only, Eastern time, **purchase date**. Proposed IANA timezone `America/New_York` (EST in winter, EDT in summer), not fixed UTC−05 all year. If fixed EST was intended, owner can correct it; bank date-only values are never timezone-shifted.
5. **Spending:** default regular; owner will mark exceptional. Annual bills should be spread over a chosen timeframe in a separate normalized view; actual transaction amounts/dates stay intact.
6. **Income:** connect owner's Chase checking through Plaid Transactions for paycheck deposits; spouse has no income. Twice-monthly around 15th/month-end remains the schedule hint.
7. **Classification:** name is **JEX**; remote classification is permitted, with preference to use the owner's existing Codex account. Treat JEX as module name, not an unidentified external package. Codex CLI subscription adapter requires separate install/login and an isolation/usage feasibility check; no agent-token scraping or assumed general API entitlement.
8. **History/imports:** approximately one year; owner will provide CSV headers later. Request 365 days at initial Plaid Link; actual history is bank-dependent.

## Remaining integration gates

- **JEX feasibility (not blocking current rules/manual MVP):** CLI installed project-locally, not authenticated. Verify supported isolated/tool-free invocation and subscription eligibility before enabling real financial classification. Owner performs dedicated login later; never request tokens in chat.
- **Plaid setup (not blocking current manual/CSV MVP):** owner supplies credentials securely outside chat when ready; confirm actual Trial dashboard and test standard Safari popup/no-redirect Link without public ingress.

## Nonblocking defaults / later questions

- **Card details:** assign owner/display names and login grouping during Link. If the latest two-Chase/two-Amex inventory was a typo, correct it before linking. Accounts, cards and institution logins are not necessarily one-to-one.
- **Eastern time:** use `America/New_York` unless fixed EST is explicitly requested.
- **Annual allocations:** propose whole-calendar-month periods chosen per transaction (default 12 months starting purchase month); separate actual and normalized totals, no double-counting. Is a different default useful? See ARCHITECTURE.md.
- **Refunds:** actual view recognizes the refund on its own purchase/authorization/fallback date; offers explicit period allocation if refund relates to a spread bill. No automatic restatement of real purchase history.
- **Checking:** ingest selected checking transactions, exclude transfers/card payments, and use employer/payroll hints plus reviewed rules for income—not every positive inflow. Owner can choose credit-only expense reporting filters if desired.
- **Schedule:** no weekend/holiday adjustment initially; actual deposits are authoritative. Schedule amounts optional.
- **Categories/events:** start with common household categories and optional named exceptional events; editable. No spending targets/envelope budget engine initially.
- **Backups:** private destination/retention still to choose before automated backups; no external upload or new startup service assumed.
- **Trust boundary:** owner accepts a LAN listener; exact guest/IoT/VPN routing and existing proxy/forwarding exposure remain unverified. Do not add firewall changes without approval or claim network isolation beyond tested evidence.

## Verified publicly vs not yet tested

Verified official documentation: Trial limits, Transactions response/signs/date fields, 365-day initial request capability, sync polling/status, and web popup OAuth without redirect URI. Not verified: owner's actual Trial activation, institution/account availability, full-year fill, private-IP Safari Link success, real payroll descriptions, subscription quota, CLI isolation, router/firewall exposure. Full sources and caveats: [INTEGRATIONS.md](INTEGRATIONS.md).
