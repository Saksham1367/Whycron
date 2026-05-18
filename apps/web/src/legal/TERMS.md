# Terms of Service

**Effective date:** 2026-05-18
**Last updated:** 2026-05-18

These Terms of Service ("Terms") form a binding agreement between you (or the organization you represent) ("Customer", "you") and Saksham Dhingra, an individual residing in Faridabad, Haryana, India, trading under the brand name Whycron ("Whycron", "we", "us"). By creating an account or using the Whycron service available at whycron.com and related domains (the "Service"), you accept these Terms.

If you do not accept these Terms, do not use the Service.

## 1. The Service

Whycron is a cron-job and scheduled-task monitoring service. You configure monitors with expected schedules; we record heartbeat pings from your jobs; if a heartbeat is missed, late, or failed, we send alerts to your configured notification channels along with an AI-generated plain-English explanation of the likely cause.

The Service is provided on an ongoing basis. Specific features available at any given time are documented at whycron.com and in the in-product UI.

## 2. Eligibility & accounts

You must be at least 16 years old to use the Service. By using the Service you represent that you meet this age requirement.

You are responsible for:

- The accuracy of the information you provide at sign-up.
- Keeping your account credentials secure. We strongly recommend Google sign-in over email/password.
- All activity that happens under your account, including by anyone you give access to.
- Keeping your ping tokens secret. A ping token is a bearer credential that anyone with the value can use to record runs against your monitor.

Notify us immediately at sakshamdhingra1305@gmail.com if you suspect unauthorized access to your account.

## 3. Plans, pricing, and billing

We offer a free tier and one or more paid tiers ("Pro"). Current pricing, limits, and feature differences are listed at whycron.com/pricing and in the dashboard.

**Merchant of Record.** Payments are processed by Polar Software Inc. ("Polar"), acting as our Merchant of Record. When you upgrade, your contract for the payment itself is with Polar. We never see, store, or process your card number.

**Billing cycle.** Pro subscriptions renew automatically each month or year (as selected) on the same calendar day, charged in advance. Local taxes are added by Polar where applicable.

**Plan changes.** You may upgrade, downgrade, or cancel any time from the Account page. Downgrades and cancellations take effect at the end of the current billing period.

**No refunds for partial periods.** Because the Service is delivered continuously, we do not provide pro-rated refunds for cancellations mid-period or for periods of non-use. You retain access until the end of the period you have paid for.

**Failed payments.** If a renewal payment fails, we will retry per Polar's standard dunning schedule. If payment cannot be collected, your workspace is downgraded to the free tier, which may reduce retention and feature limits.

## 4. Acceptable use

You may not, and may not permit anyone else to:

- Use the Service to monitor jobs that perform illegal activity, harass third parties, or violate any law applicable to you or to us.
- Send personally identifiable information of third parties through the ping API beyond what is incidentally present in legitimate job output. We are not a customer-data processor — we are a monitoring tool.
- Attempt to circumvent the redactor (§4 of PRIVACY.md) by encoding secrets in a way designed to evade pattern matching.
- Reverse-engineer the Service except to the limited extent permitted by mandatory applicable law.
- Resell the Service or operate it as part of a service-bureau offering without our written permission.
- Send abusive traffic — automated ping floods unrelated to a legitimate monitored workload, traffic intended to disrupt the Service, or traffic intended to consume free-tier resources at scale.
- Use the Service to send unsolicited messages ("spam") via the Brevo, Discord, Slack, or webhook channels.

We may suspend or terminate accounts that violate this section. For egregious violations we may do so without prior notice.

## 5. Beta features

We may label specific features as "beta" or "experimental". Beta features are provided as-is, may change without notice, may be discontinued, and may have lower reliability than the rest of the Service. SLA commitments (if any) do not apply to beta features.

## 6. Your data

Your use of the Service involves the processing of personal data and operational data as described in our [Privacy Policy](PRIVACY.md), which is incorporated into these Terms by reference.

You retain all rights, title, and interest in your data ("Customer Data"). You grant us a worldwide, non-exclusive license to host, process, transmit, display, and otherwise use Customer Data solely to provide and improve the Service for you, including by passing redacted log excerpts to Anthropic for explanation generation.

You are responsible for ensuring that you have the right to send Customer Data to the Service and that doing so does not violate any law or any agreement you have with a third party.

## 7. Availability and SLA

We aim for high availability but do not commit to a specific uptime percentage on the free tier. Pro-tier service-level commitments, if any, are documented in your plan description on whycron.com/pricing.

We may from time to time:

- Perform scheduled maintenance, with advance notice where practical.
- Apply emergency security patches without notice.
- Throttle or temporarily suspend accounts whose traffic threatens overall Service stability.

## 8. Intellectual property

The Service, including its source code, design, brand, and documentation, is the property of Saksham Dhingra and is protected by applicable IP laws. These Terms do not transfer any IP rights to you. Open-source components are governed by their respective licenses (see the repository).

The "Whycron" name and logo are our trademarks. You may use them only to refer to the Service truthfully; you may not use them to imply endorsement of your product without written permission.

## 9. Feedback

If you send us feedback, suggestions, or feature requests, you grant us a perpetual, irrevocable, royalty-free license to use that feedback for any purpose, including incorporating it into the Service, without obligation to you. We will not publish your name in connection with feedback without your permission.

## 10. Third-party services

The Service integrates with third-party services you choose to connect (Slack, Discord, generic webhooks, your email provider, etc.). Your use of those services is governed by their own terms. We are not responsible for the availability, security, or behavior of any third-party service.

## 11. Termination

**By you.** You may cancel any time from the Account page; cancellation takes effect at the end of the current billing period. To fully delete your account and data, use the deletion endpoint or write to us — see PRIVACY.md §7.

**By us.** We may suspend or terminate your account, with or without notice, if you violate these Terms (especially §4), if required by law, or if we discontinue the Service. We will give at least 30 days' notice before discontinuing the Service entirely, except where impractical for legal or security reasons.

**Survival.** Sections 6 (Your data — retention obligations), 8 (IP), 9 (Feedback), 12 (Disclaimers), 13 (Limitation of liability), 14 (Indemnification), 16 (Governing law), and any provision that by its nature should survive, will survive termination.

## 12. Disclaimers

THE SERVICE IS PROVIDED "AS IS" AND "AS AVAILABLE", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO IMPLIED WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, ACCURACY, OR NON-INFRINGEMENT.

In particular, the AI-generated failure explanations are produced by a third-party large language model and may be incorrect, incomplete, or misleading. They are intended to assist your debugging, not to replace your judgment. You remain responsible for diagnosing and fixing your own jobs.

We do not warrant that the Service will be uninterrupted, error-free, or completely secure.

## 13. Limitation of liability

TO THE MAXIMUM EXTENT PERMITTED BY LAW:

- NEITHER PARTY WILL BE LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING LOST PROFITS, LOST REVENUE, LOST DATA, OR BUSINESS INTERRUPTION, EVEN IF ADVISED OF THE POSSIBILITY.
- OUR TOTAL CUMULATIVE LIABILITY FOR ANY AND ALL CLAIMS ARISING OUT OF OR RELATING TO THESE TERMS OR THE SERVICE WILL NOT EXCEED THE GREATER OF (A) THE FEES YOU ACTUALLY PAID US IN THE 12 MONTHS PRECEDING THE EVENT GIVING RISE TO THE CLAIM, OR (B) USD 100.

These limitations apply regardless of the legal theory (contract, tort, statute, or otherwise) and even if a limited remedy fails of its essential purpose. They do not apply to liability that cannot be limited under applicable law (for example, gross negligence or willful misconduct under Indian law).

## 14. Indemnification

You will defend, indemnify, and hold harmless the Operator from and against any claim, loss, or expense (including reasonable attorneys' fees) arising out of (a) your violation of these Terms, (b) your violation of any law or of the rights of any third party, or (c) Customer Data, including any claim that Customer Data infringes a third party's rights.

## 15. Changes to these Terms

We may update these Terms. Material changes will be announced by email to the account owner at least 14 days before taking effect, and the "Last updated" date will change. Continued use of the Service after the effective date constitutes acceptance. If you do not agree to the updated Terms, your remedy is to stop using the Service and cancel your subscription.

## 16. Governing law and dispute resolution

These Terms are governed by the laws of the Republic of India, without regard to its conflict-of-laws rules. The United Nations Convention on Contracts for the International Sale of Goods does not apply.

The courts located in Faridabad, Haryana, India have exclusive jurisdiction over any dispute arising out of or relating to these Terms or the Service, and you consent to the personal jurisdiction of those courts. Nothing in this section limits your statutory rights as a consumer under your local law.

## 17. Notices

We may send notices to you at the email address on your account. You should send notices to us at **sakshamdhingra1305@gmail.com**. Notices are deemed received when sent.

## 18. Miscellaneous

**Entire agreement.** These Terms, together with the Privacy Policy and any plan-specific terms presented at sign-up, are the entire agreement between you and us regarding the Service and supersede any prior agreement on the same subject.

**No assignment.** You may not assign these Terms without our written consent. We may assign these Terms to a successor in connection with a merger, acquisition, or sale of substantially all of our assets.

**Severability.** If any provision of these Terms is found unenforceable, the rest remain in effect.

**No waiver.** Our failure to enforce any provision is not a waiver of our right to enforce it later.

**No agency.** Nothing in these Terms creates a partnership, joint venture, employment, or agency relationship.

## 19. Contact

**Saksham Dhingra**
Operator of Whycron
Faridabad, Haryana, India
**sakshamdhingra1305@gmail.com**
