// Final legal content for Super Bajaar (a brand of KPMC Enterprises, a proprietorship concern).
// Inline markup: **bold** and [label](href). Internal links use /pages/<slug>.
// Block types: string = paragraph, {ul:[...]}, {ol:[...]}, {table:{head:[...],rows:[[...]]}}.

export const BUSINESS = {
  brand: "Super Bajaar",
  entity: "KPMC Enterprises",
  constitution: "Proprietorship concern",
  udyam: "UDYAM-JH-18-0013737",
  address: "Flat/Door No. 1104, C/o Tejni Devi Bhavan (Ambika Prasad Singh), Sikka, Pandwa, Nawdiha, Block Pandwa, Daltonganj, District Palamu, Jharkhand \u2013 822123, India",
  phone: "+91 76448 41104",
  supportEmail: "kpmcenterprise@gmail.com",
  grievanceOfficer: "NK Singh",
  grievanceEmail: "nibandhansingh1997@gmail.com",
  effective: "27 November 2026",
};

const EFFECTIVE = "**Effective date:** " + BUSINESS.effective + " \u00b7 **Version:** 1.0";
const CONTACT = "**KPMC Enterprises** (brand: Super Bajaar)\nRegistered office: " + BUSINESS.address + "\nEmail: " + BUSINESS.supportEmail + " \u00b7 Phone/WhatsApp: " + BUSINESS.phone;

export const LEGAL_PAGES = {
  "terms-and-conditions": {
    kicker: "TERMS OF USE & SALE",
    title: "Terms & Conditions",
    sections: [
      { p: [EFFECTIVE,
        "These Terms & Conditions (\u201cTerms\u201d) govern your access to and use of the Super Bajaar website and related services (the \u201cPlatform\u201d) and every purchase you make through it. By browsing the Platform, creating an account or placing an order, you confirm that you have read, understood and agree to these Terms together with our [Privacy Policy](/pages/privacy-policy), [Cookie Policy](/pages/cookie-policy), [Payment Terms](/pages/payment-information), [Shipping & Delivery Policy](/pages/shipping-delivery), [Cancellation Policy](/pages/cancellation-policy), [Returns & Refunds Policy](/pages/returns-refunds), [Super Coins & Referral Terms](/pages/loyalty-terms) and [Category-Specific Terms](/pages/category-terms), all of which form part of this agreement. If you do not agree, please do not use the Platform.",
        "Nothing in these Terms limits any right you have as a consumer under the Consumer Protection Act, 2019 or any other law that cannot be excluded by agreement."] },
      { h: "1. Who we are", p: ["Super Bajaar is a retail brand owned and operated by **KPMC Enterprises**, a proprietorship concern registered under the Udyam scheme (Udyam Registration No. " + BUSINESS.udyam + "), with its registered office at " + BUSINESS.address + ". In these Terms, \u201cwe\u201d, \u201cus\u201d and \u201cour\u201d mean KPMC Enterprises acting through its proprietor, and \u201cyou\u201d means any person who uses the Platform.",
        "Unless a product page expressly names another seller, products on the Platform are sold by KPMC Enterprises. If a third-party seller is ever onboarded, that seller\u2019s name, address and contact details will be shown on the product page before you buy."] },
      { h: "2. Eligibility and your account", p: [
        "You must be at least 18 years old and capable of entering into a binding contract under the Indian Contract Act, 1872 to place an order. A parent or lawful guardian may place an order on behalf of a minor and is responsible for that use.",
        "You may browse without an account, but you need an account to check out, save addresses, earn Super Coins, post reviews and use support tickets. You must give accurate and current information, keep your credentials confidential and tell us promptly if you suspect unauthorised use. You are responsible for activity under your account unless it results from our failure to maintain reasonable security."] },
      { h: "3. Products and listings", p: [
        "We try to describe products, images, specifications, ingredients, weights, sizes and availability accurately. Images are illustrative; packaging, colour, shade and presentation may vary within reasonable limits without being a defect. Packaged goods carry the declarations required by the Legal Metrology (Packaged Commodities) Rules, 2011, and the country of origin, expiry or best-before date and similar details are shown where the law requires.",
        "All products are subject to availability. We may limit quantities, withdraw a product or decline an order where stock, serviceability, safety, regulatory or fraud-prevention concerns arise. Category-specific conditions are in our [Category-Specific Terms](/pages/category-terms)."] },
      { h: "4. Prices, taxes and errors", p: [
        "All prices are in Indian Rupees. Prices shown are the final price payable, inclusive of all applicable taxes, if any, and shall not exceed the Maximum Retail Price printed on the product. Delivery charges, if any (for example the express delivery fee), and any discount, Super Coins redemption or other adjustment are shown to you before you pay, and the amount you pay is the total shown on the final checkout screen. We do not add undisclosed charges after you reach payment.",
        "Where a product page shows the lowest price in the previous 30 days, it is for your reference. If a product is listed at an obvious pricing or typographical error, we may cancel the affected order before dispatch and refund any amount paid in full, rather than supply the product at the erroneous price. We will tell you before doing so."] },
      { h: "5. Placing an order and contract formation", p: [
        "Your order is an offer to buy. When you complete payment, you will see an on-screen confirmation and receive an order number; this acknowledges receipt and is not by itself our acceptance. A binding contract of sale is formed for each item when we confirm the order for dispatch. If we cannot supply an item, we will tell you, cancel that item and refund any amount already paid for it under the [Cancellation Policy](/pages/cancellation-policy).",
        "We may refuse or cancel an order for reasons such as: stock unavailability, a delivery address that is not serviceable, inaccurate information, suspected fraud or misuse of offers, failure of payment verification, or events beyond our control. You will be informed and refunded for any amount paid."] },
      { h: "6. Payment", p: ["Online payments are processed through Razorpay\u2019s secure checkout. An order is treated as paid only after the payment is verified as successful by the payment provider and matched to your order and amount. Full details, including failed and duplicate payments, are in our [Payment Terms](/pages/payment-information)."] },
      { h: "7. Delivery", p: ["We deliver to serviceable PIN codes across the areas shown at checkout. Delivery options, estimated timelines and charges are explained in our [Shipping & Delivery Policy](/pages/shipping-delivery). Delivery timelines are estimates, not guarantees, and risk in the goods passes to you on delivery."] },
      { h: "8. Cancellations, returns and refunds", p: ["You may cancel an order, or return a product, as set out in our [Cancellation Policy](/pages/cancellation-policy) and [Returns & Refunds Policy](/pages/returns-refunds). Approved refunds are processed within 2 working days after verification and approval, to the original payment method wherever possible."] },
      { h: "9. Super Coins, referrals and offers", p: ["Super Coins, referral rewards, coupons and promotional offers are governed by the [Super Coins & Referral Terms](/pages/loyalty-terms) and by any conditions shown with a specific offer. Offers are for personal, non-commercial use and may be withdrawn for misuse."] },
      { h: "10. Reviews and content you submit", p: [
        "You may post product reviews, ratings, photos and support attachments (\u201cUser Content\u201d). You remain the owner of your User Content, but you grant us a non-exclusive, royalty-free, worldwide, perpetual licence to host, display, reproduce, adapt and use it on the Platform and in our marketing for the Super Bajaar brand. You confirm that you have the right to give this licence.",
        "Reviews should reflect your genuine experience. We do not pay for or edit reviews to change their sentiment, and we may moderate or remove content that breaks these Terms or the law. User Content must not:"],
        ul: ["be false, misleading, defamatory, obscene, hateful, harassing or invasive of another person\u2019s privacy;",
          "infringe any copyright, trademark or other right, or contain personal data of others;",
          "contain advertising, spam, links to other sites, or content posted by or for a competitor or in return for payment not disclosed;",
          "contain viruses or anything that could harm the Platform."] },
      { p: ["If you believe any content on the Platform is unlawful or infringes your rights, write to our Grievance Officer (see the [Grievance Redressal](/pages/grievance-redressal) page) with the details. We will act on valid notices in accordance with the Information Technology Act, 2000 and the Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021."] },
      { h: "11. Acceptable use", p: ["You agree not to:"], ul: [
        "use the Platform for any unlawful purpose or place orders for resale, commercial bulk purchase or fraudulent purposes without our written approval;",
        "provide false identity, address or payment details, or use another person\u2019s payment instrument without authority;",
        "scrape, crawl, copy, reverse-engineer, overload or interfere with the Platform, or bypass its security or access controls;",
        "attempt to access any administrative area, another customer\u2019s account or data, or any system that is not meant for you;",
        "abuse offers, referral or Super Coins features, including through multiple or fake accounts."] },
      { h: "12. Intellectual property", p: [
        "The Super Bajaar name, logo, website design, text, graphics, software and other content are the property of KPMC Enterprises or its licensors and are protected by Indian intellectual property law. Product names and trademarks of brands we sell belong to their respective owners, and their use on the Platform does not imply endorsement.",
        "We grant you a limited, personal, non-exclusive, non-transferable and revocable permission to access and use the Platform for personal, non-commercial shopping. You may not copy, republish, sell or commercially exploit any part of the Platform without our prior written consent."] },
      { h: "13. Third-party services and links", p: ["The Platform may use or link to third-party services (such as payment, courier, analytics and communication services). Their services are governed by their own terms and privacy policies. We are not responsible for the content or practices of third-party sites we do not operate."] },
      { h: "14. Warranties and disclaimers", p: [
        "Products carry the warranty and guarantee, if any, given by their manufacturer or brand; where the law requires a warranty or guarantee card, it is supplied with the product. We confirm that goods will be of the quality and description shown, as required under applicable consumer and sale-of-goods law.",
        "Subject to the foregoing and to the extent permitted by law, the Platform is provided on an \u201cas available\u201d basis. We do not warrant that it will be uninterrupted or error-free, and we may suspend it for maintenance or security. Information on the Platform is for general shopping purposes and is not professional, medical, legal, financial or insurance advice."] },
      { h: "15. Limitation of liability", p: [
        "To the maximum extent permitted by law, KPMC Enterprises will not be liable for any indirect, incidental, special or consequential loss, or for loss of profit, data or goodwill, arising from your use of the Platform or a purchase. Our total liability for any claim relating to an order is limited to the amount you paid for that order.",
        "This clause does not exclude or limit liability for death or personal injury caused by our negligence, for fraud, for defective goods or deficiency in service for which a consumer remedy is available under law, or for anything else that cannot lawfully be limited."] },
      { h: "16. Indemnity", p: ["You agree to compensate KPMC Enterprises for reasonable losses and legal costs that arise from your breach of these Terms, your unlawful use of the Platform, or your User Content infringing a third party\u2019s rights, to the extent permitted by law."] },
      { h: "17. Suspension and termination", p: ["We may suspend or close an account, restrict access or cancel orders where we reasonably believe there is fraud, abuse, breach of these Terms or legal requirement. You may stop using the Platform and request deletion of your account at any time, subject to records we must retain by law and to any pending orders or refunds."] },
      { h: "18. Events beyond our control", p: ["We are not liable for delay or failure caused by events beyond our reasonable control, including natural disasters, floods, strikes, road or rail closures, epidemics, government orders, power or network failure, or failure of third-party services. Where this prevents an order being fulfilled, we will offer a refund of the amount paid for the affected items."] },
      { h: "19. Electronic records and communications", p: ["These Terms and all policies are electronic records under the Information Technology Act, 2000 and need no signature. You agree that we may send order, delivery, payment, refund and support messages by email, SMS, in-app notice or WhatsApp to the contact details you provide. Promotional messages are sent only where you have agreed to receive them, and you can opt out at any time through the link or option in the message or by contacting us."] },
      { h: "20. Governing law and disputes", p: [
        "These Terms are governed by the laws of India. Please first raise any complaint with our Grievance Officer as described on the [Grievance Redressal](/pages/grievance-redressal) page; most issues can be resolved there quickly.",
        "If a dispute is not resolved, you may approach the appropriate Consumer Disputes Redressal Commission, and as a consumer you may file a complaint where you reside or work, as the Consumer Protection Act, 2019 allows. Subject to that and to any other mandatory right, the courts at Daltonganj (Medininagar), Palamu, Jharkhand have exclusive jurisdiction over disputes arising from these Terms."] },
      { h: "21. Changes to these Terms", p: ["We may update these Terms to reflect changes in our services or the law. The updated version applies from the effective date shown on it, and orders already placed are governed by the Terms in force when you placed them. Where a change is material, we will give reasonable notice on the Platform."] },
      { h: "22. General", p: ["If any provision is held unenforceable, the rest remain in force. Our failure to enforce a right is not a waiver of it. These Terms, with the policies linked above, are the entire agreement between you and us about the Platform and replace earlier understandings on the same subject. You may not assign your rights under these Terms; we may assign ours to a successor of the business."] },
      { h: "23. Contact", p: [CONTACT] },
    ],
  },

  "privacy-policy": {
    kicker: "YOUR INFORMATION & PRIVACY",
    title: "Privacy Policy",
    sections: [
      { p: [EFFECTIVE,
        "**KPMC Enterprises** (brand: Super Bajaar) (\u201cwe\u201d) is the data fiduciary for personal data collected through the Super Bajaar website and services. This policy explains what we collect, why, who receives it, how long we keep it and what choices you have. It is written to meet the Information Technology Act, 2000 and the rules under it, and the Digital Personal Data Protection Act, 2023 and Digital Personal Data Protection Rules, 2025, as their provisions come into force. By using the Platform you acknowledge this policy; where the law requires your consent for a specific purpose, we ask for it separately."] },
      { h: "1. Personal data we collect", p: ["We collect only what we need:"], ul: [
        "**Account and contact data:** name, email address, mobile number and password (stored in protected form) when you register.",
        "**Delivery data:** recipient name, phone number, full address, landmark and PIN code you save for delivery.",
        "**Order and payment data:** items bought, amounts, delivery option, order and payment status, and provider references. Card, UPI and bank credentials are entered on Razorpay\u2019s secure checkout; we do not see or store your full card number, CVV, UPI PIN or OTP.",
        "**Support data:** messages, tickets, attachments (such as photos of a damaged item), return requests and grievances.",
        "**Rewards data:** Super Coins balance and history, and referral links between accounts.",
        "**Reviews and wishlist:** ratings, review text and photos, and items you save.",
        "**Technical data:** IP address, device and browser type, pages viewed and security logs; and, only if you accept analytics, aggregated usage data collected through Google Analytics."] },
      { h: "2. Why we use it", p: ["We process personal data to:"], ul: [
        "create and secure your account, and verify orders and returns;",
        "check delivery availability, process and deliver orders, collect payments and issue refunds and invoices;",
        "provide support and resolve grievances;",
        "run Super Coins, referral and offers;",
        "send service messages about your order (these are not marketing);",
        "send marketing or offers only where you have agreed;",
        "improve the Platform, understand usage (with consent), and prevent fraud, abuse and security incidents;",
        "keep records and meet legal, tax, accounting and regulatory duties."] },
      { p: ["Our legal basis is your consent, the performance of the purchase you asked for, and \u201clegitimate uses\u201d recognised by law, such as complying with legal obligations and responding to a request from you."] },
      { h: "3. Who we share it with", p: ["We do not sell your personal data. We share it only as needed, with:"], ul: [
        "**Razorpay** (payment processing, fraud screening and refunds);",
        "**delivery and logistics partners** (name, phone, address and order contents needed to deliver to you);",
        "**technology service providers** for hosting, storage, email/SMS/WhatsApp communication and security, who act on our instructions;",
        "**Google Analytics**, only if you accept analytics cookies;",
        "**professional advisers, auditors, banks and insurers** where needed for accounting, tax, legal or risk purposes;",
        "**courts, regulators and law-enforcement authorities** where required by law or to protect rights and safety."] },
      { p: ["We ask these parties to protect your data and use it only for the stated purpose. Some providers (for example Google) may process data on servers outside India; the law permits this subject to any restriction the Government notifies."] },
      { h: "4. Cookies and browser storage", p: ["The Platform stores some information in your browser (for example your basket, wishlist, delivery PIN, sign-in session and your analytics choice). Strictly necessary storage is used without consent; analytics runs only after you accept. See our [Cookie Policy](/pages/cookie-policy) for the full list and how to change your choice."] },
      { h: "5. How long we keep data", p: [], table: { head: ["Data", "Retention"], rows: [
        ["Account and profile", "While your account is active, and until you ask us to delete it (subject to the rows below)"],
        ["Order, invoice, payment and refund records", "At least 6 years, or longer if tax, accounting or other law requires"],
        ["Support tickets, returns and grievances", "Up to 3 years after closure, to deal with disputes and follow-up"],
        ["Security and access logs", "At least 180 days, or longer where law or an investigation requires"],
        ["Analytics data", "Up to 14 months, in aggregated form"],
        ["Marketing preferences", "Until you withdraw consent"],
      ] } },
      { p: ["When data is no longer needed, we delete it or make it anonymous, unless law requires us to keep it."] },
      { h: "6. Security", p: ["We use reasonable technical and organisational measures, including access controls, encrypted connections (HTTPS), role-based staff access and monitoring, to protect personal data against loss, misuse and unauthorised access. No system is completely secure, so please use a strong, unique password and never share your OTP or PIN. If a breach affecting your personal data occurs, we will inform you and the authorities as the law requires."] },
      { h: "7. Your rights", p: ["Subject to the law, you may:"], ul: [
        "ask for a summary of the personal data we hold and how it is processed, and who it was shared with;",
        "correct inaccurate data and complete or update it;",
        "ask us to erase your data, unless we need to keep it for a lawful purpose;",
        "withdraw consent at any time (this does not affect processing already done, and may limit services that depend on that data);",
        "get your grievance resolved, and nominate another person to exercise your rights in the event of your death or incapacity."] },
      { p: ["To exercise a right, write to the Grievance Officer below. We may ask you to verify your identity first. We aim to respond within 30 days, and in any case within the time the law prescribes. If you remain dissatisfied, you may complain to the Data Protection Board of India once that mechanism is in force."] },
      { h: "8. Children", p: ["The Platform is for adults. We do not knowingly collect personal data of a child (a person under 18) without verifiable consent of a parent or lawful guardian, and we do not track or target children with advertising. If you believe a child has given us data without consent, contact us and we will delete it."] },
      { h: "9. Marketing messages", p: ["We send promotional messages only with your consent. You can opt out of marketing at any time using the unsubscribe option or by contacting us; we will still send essential messages about orders, payments, deliveries and your account."] },
      { h: "10. Changes", p: ["We may update this policy as our services or the law change. The updated version will show a new effective date, and we will give notice of material changes on the Platform."] },
      { h: "11. Contact and Grievance Officer", p: ["**Grievance Officer:** " + BUSINESS.grievanceOfficer + "\nEmail: " + BUSINESS.grievanceEmail + " \u00b7 Phone: " + BUSINESS.phone + "\nAddress: " + BUSINESS.entity + ", " + BUSINESS.address] },
    ],
  },

  "cookie-policy": {
    kicker: "COOKIES & BROWSER STORAGE",
    title: "Cookie Policy",
    sections: [
      { p: [EFFECTIVE,
        "This policy explains how the Super Bajaar website uses cookies and similar browser storage on your device. It should be read with our [Privacy Policy](/pages/privacy-policy)."] },
      { h: "What we store", p: [], table: { head: ["Item", "Purpose", "Type"], rows: [
        ["Basket (sb-cart)", "Remembers the items in your basket", "Necessary"],
        ["Wishlist (sb-wishlist)", "Remembers products you saved", "Necessary / preference"],
        ["Customer sign-in session", "Keeps you signed in securely", "Necessary"],
        ["Delivery PIN (sb-delivery-pin)", "Shows delivery availability for your area", "Preference"],
        ["Saved profile details", "Pre-fills checkout details on your device", "Preference"],
        ["Analytics choice (sb.analytics.consent)", "Records whether you accepted or declined analytics", "Necessary"],
        ["Google Analytics", "Measures page views and shopping behaviour in aggregate to improve the store", "Analytics (only with your consent)"],
      ] } },
      { h: "Your choices", p: [
        "Necessary and preference storage is needed for the store to work and is used without separate consent. Google Analytics is switched on only if you accept analytics, and we configure it with advertising signals turned off. You can change your decision at any time from the cookie notice on the Platform, or by clearing the site\u2019s data in your browser settings.",
        "Blocking necessary storage may stop the basket, sign-in or checkout from working. We do not use cookies to sell your personal data."] },
      { h: "Third parties", p: ["Razorpay\u2019s checkout (loaded when you pay) and Google Analytics (if accepted) may set their own cookies, which are governed by their policies."] },
    ],
  },

  "payment-information": {
    kicker: "PAYMENT TERMS",
    title: "Payment Terms",
    sections: [
      { p: [EFFECTIVE,
        "These terms explain how payments work on the Super Bajaar website, operated by KPMC Enterprises. They form part of our [Terms & Conditions](/pages/terms-and-conditions)."] },
      { h: "1. Payment methods", p: ["All prices are in Indian Rupees (\u20b9). Online payments are collected through **Razorpay**, a payment gateway, which offers the methods shown at checkout, such as UPI, debit and credit cards, net banking and wallets. Only the methods shown on the checkout screen are available for an order. Please check the final amount before you pay."] },
      { h: "2. How your payment is confirmed", p: ["An order is treated as paid only after Razorpay\u2019s secure server confirmation is verified and matched to your order and amount. A screenshot, SMS or browser redirect alone is not proof of payment. If the confirmation does not arrive, the order stays unpaid and will not be processed."] },
      { h: "3. Super Coins at checkout", p: ["Where Super Coins redemption is available, 1 Super Coin equals \u20b91 of discount, and at least \u20b91 of each order must be paid online. See the [Super Coins & Referral Terms](/pages/loyalty-terms)."] },
      { h: "4. Failed, pending and duplicate payments", p: [
        "If your account is debited but the order shows unpaid or failed, please do not pay again straight away. In most cases the bank or Razorpay reverses the amount automatically within about 5\u20137 working days. If it does not, contact us with your order number and transaction reference and we will check the provider\u2019s records and either confirm the order or refund the amount.",
        "If you are charged more than once for the same order, the extra amount will be refunded to the original payment method after verification."] },
      { h: "5. Security", p: ["Your card, UPI and bank details are entered only on Razorpay\u2019s secure checkout, which follows card-industry security standards; we do not store them. Never share your card PIN, CVV, UPI PIN, password or OTP with anyone, including our staff. We will never ask for them by phone, email or chat. Do not pay to any bank account, QR code or payment link sent outside the official website."] },
      { h: "6. Fraud prevention", p: ["We and our payment provider may run checks to detect fraud. We may hold, cancel or refuse an order where a payment appears unauthorised or suspicious, and we will refund any amount collected."] },
      { h: "7. Refunds", p: ["Approved refunds are made to the original payment method, wherever possible, within 2 working days after verification and approval, as set out in the [Returns & Refunds Policy](/pages/returns-refunds). Your bank or payment provider may take a few more working days to show the credit."] },
      { h: "8. Chargebacks", p: ["If you raise a chargeback with your bank for an order that is already being handled through us, please tell us first so we can resolve it quickly. We may share the order information with the bank and Razorpay to respond to a chargeback."] },
      { h: "9. Invoices and taxes", p: ["An invoice or bill is issued for each order and is available in your account or by email. The price shown is the final price payable. KPMC Enterprises is not currently registered under GST, so no GST is charged separately. Once registered, GST invoices will be issued and this policy updated."] },
      { h: "10. Payment support", p: ["For payment help, email " + BUSINESS.supportEmail + " or call " + BUSINESS.phone + " with your order number. Never send card details, OTPs or passwords."] },
    ],
  },

  "shipping-delivery": {
    kicker: "DELIVERY INFORMATION",
    title: "Shipping & Delivery Policy",
    sections: [
      { p: [EFFECTIVE] },
      { h: "1. Delivery options", p: [], table: { head: ["Option", "Estimated time", "Charge"], rows: [
        ["Standard delivery", "Usually 1\u20135 days from order confirmation", "As shown at checkout"],
        ["Express delivery (eligible items and PIN codes only)", "30 minutes to 1 day", "\u20b939 per order"],
      ] } },
      { p: ["Express delivery is offered only where every item in your basket is eligible and your PIN code is serviceable; if it is not available, checkout will show standard delivery only. Delivery charges are shown before you pay."] },
      { h: "2. Serviceability", p: ["Enter your six-digit PIN code on the store to check whether we deliver to you. We deliver only to serviceable PIN codes, and some products may not be available in every area."] },
      { h: "3. Delivery timelines", p: ["Timelines are estimates counted from order confirmation, and may be affected by stock, location, weather, road conditions, public holidays or other operational reasons. A delay is not by itself a ground to cancel, but if an order is materially delayed you may contact us and we will help, including with cancellation and refund where appropriate."] },
      { h: "4. Delivery process", p: [
        "Orders are delivered to the address you select at checkout; please make sure the address, PIN code, landmark and phone number are correct, and that someone is available to receive the order. We may contact you by phone or WhatsApp to confirm the address or arrange delivery.",
        "Please check the package at delivery. If it appears tampered with, damaged or wet, tell the delivery person and contact us within the time given in the [Returns & Refunds Policy](/pages/returns-refunds)."] },
      { h: "5. Failed delivery", p: ["If delivery cannot be completed because you are unreachable, the address is wrong or incomplete, or the order is refused without a valid reason, we will make reasonable attempts to reach you. If delivery still fails, the order may be cancelled and returned to us. We will refund the amount paid for the items, but the express delivery fee is not refundable where the failure is due to you. Perishable items cannot be re-delivered once they have been out for delivery."] },
      { h: "6. Partial shipments", p: ["An order with several items may arrive in more than one package. You will not be charged extra delivery for a split shipment that we choose to make. If an item is unavailable, we will inform you and refund its price."] },
      { h: "7. Ownership and risk", p: ["Ownership and risk in the goods pass to you when the order is delivered to the address you gave."] },
      { h: "8. Delivery help", p: ["Call " + BUSINESS.phone + " or email " + BUSINESS.supportEmail + " with your order number."] },
    ],
  },

  "cancellation-policy": {
    kicker: "ORDERS & CANCELLATIONS",
    title: "Cancellation Policy",
    sections: [
      { p: [EFFECTIVE] },
      { h: "1. Cancelling an order", p: [], table: { head: ["Order status", "Can you cancel?", "What happens"], rows: [
        ["Placed or being prepared (not yet packed)", "Yes", "Full refund of the amount paid, with no cancellation charge"],
        ["Packed or handed to the delivery partner", "On request, subject to the partner\u2019s stage", "If it can be stopped, full refund; otherwise refuse delivery or use the return process"],
        ["Out for delivery or delivered", "No cancellation", "Use the [Returns & Refunds Policy](/pages/returns-refunds) where eligible"],
      ] } },
      { p: ["To cancel, contact us as soon as possible with your order number: call or WhatsApp " + BUSINESS.phone + ", email " + BUSINESS.supportEmail + ", or raise a ticket from My Account. We will confirm the cancellation in writing."] },
      { h: "2. Items that cannot be cancelled once processing begins", p: ["Perishable and fresh items, made-to-order or personalised products, and medicines once packed for dispatch, may not be cancellable once preparation has begun. This will be indicated on the product page or when you contact us."] },
      { h: "3. Cancellation by us", p: ["We may cancel an order, in whole or in part, for stock unavailability, pricing or listing errors, non-serviceable address, suspected fraud, failed payment verification, regulatory reasons or events beyond our control. We will inform you and refund the amount paid for the cancelled items in full."] },
      { h: "4. Refunds on cancellation", p: ["Where a paid order is cancelled, we will refund the amount to the original payment method within 2 working days after the cancellation is confirmed. Your bank or payment provider may take a few more working days to credit it. Super Coins used on a cancelled order are restored to your account, and Super Coins that were earned on it will not be credited."] },
      { h: "5. Partial cancellation", p: ["You may ask to cancel one or more items in an order before it is packed. We will refund those items. A delivery fee already charged will be refunded only if the whole order is cancelled or where the cancellation is due to us."] },
      { h: "6. Your statutory rights", p: ["This policy does not affect any right you have under the Consumer Protection Act, 2019 or other applicable law."] },
    ],
  },

  "returns-refunds": {
    kicker: "RETURNS & REFUNDS",
    title: "Returns & Refunds Policy",
    sections: [
      { p: [EFFECTIVE] },
      { h: "1. When you can return an item", p: ["You may request a return or replacement within **7 days of delivery** if the item is:"], ul: [
        "damaged, defective or not working on arrival;",
        "different from what you ordered, or missing from the package;",
        "expired or close to expiry beyond what was stated, or materially different from the listing."] },
      { p: ["For **fresh produce, dairy, bakery and other perishables**, please report within **24 hours** of delivery. Report the problem through My Account, WhatsApp, phone or email, with your order number and clear photos (and a photo of the label, batch or packaging where relevant)."] },
      { h: "2. Change-of-mind returns", p: ["Where a product page marks an item as returnable, you may return it within 7 days of delivery if it is unused, unopened, in original packaging with all tags, accessories and invoice. Return pick-up charges for a change-of-mind return, if any, will be told to you before you confirm the request."] },
      { h: "3. Items that cannot be returned", p: ["Unless they are damaged, defective, wrong or expired, the following cannot be returned, in line with applicable law and where this is disclosed before purchase:"], ul: [
        "perishable and fresh goods, food and grocery items once delivered in good condition;",
        "opened or used personal care, hygiene, beauty, innerwear and similar products, and items with a broken seal;",
        "medicines and health products (see [Category-Specific Terms](/pages/category-terms));",
        "made-to-order, personalised or customised items, and gift cards or vouchers;",
        "insurance or other services once delivered;",
        "items damaged by misuse, or returned without original packaging or parts."] },
      { h: "4. How a return works", p: [] , ol: [
        "Contact us within the time limit and share your order number, the reason and photos.",
        "We review the request and tell you whether it is approved; we may ask for more information.",
        "If approved, we arrange pick-up, or tell you how to return the item. Where the return is due to our error or a defect, there is no cost to you.",
        "We inspect the returned item to confirm it is genuine and matches the reason given.",
        "After verification and approval, we issue a refund or replacement."] },
      { h: "5. Refund timing and method", p: [
        "Genuine and verified returns approved for a refund will be processed within **2 working days** after verification and approval. Refunds go to the original payment method, wherever possible. Your bank, card issuer or wallet may take additional working days to show the credit, which is outside our control.",
        "Where a product is partly returned, the refund covers only the returned items. A delivery or express fee is refunded only if the return is due to our error, a defect or a wrong item."] },
      { h: "6. Super Coins", p: ["Super Coins used on a returned item are restored to your account in proportion to the refund. Super Coins earned on a returned item are reversed. See the [Super Coins & Referral Terms](/pages/loyalty-terms)."] },
      { h: "7. Replacements", p: ["Where you prefer a replacement and stock is available, we will send one at no extra cost. If it is unavailable, we will offer a refund."] },
      { h: "8. Brand warranty issues", p: ["For electronics and appliances that fail after the return window, the manufacturer\u2019s warranty applies. We will help you contact the brand\u2019s service centre where possible."] },
      { h: "9. Disputes", p: ["If you disagree with a decision on a return or refund, write to our Grievance Officer through the [Grievance Redressal](/pages/grievance-redressal) page. Nothing in this policy limits your rights under the Consumer Protection Act, 2019."] },
    ],
  },

  "loyalty-terms": {
    kicker: "REWARDS TERMS",
    title: "Super Coins & Referral Terms",
    sections: [
      { p: [EFFECTIVE,
        "These terms govern the Super Coins loyalty programme and referral rewards run by KPMC Enterprises for the Super Bajaar brand. They are part of our [Terms & Conditions](/pages/terms-and-conditions)."] },
      { h: "1. Joining", p: ["The programme is open to registered customers aged 18 or over. Participation is free."] },
      { h: "2. Earning Super Coins", p: [
        "You earn Super Coins on eligible purchases at the rate shown on the store (the standard rate is 1 coin for every \u20b9100 of eligible spend), or a different rate where a product or category shows one. Coins are credited only **after delivery is confirmed**, not when the order is placed.",
        "Taxes, delivery and other charges, gift cards and any amount paid with Super Coins may not earn coins. Coins are credited in whole numbers."] },
      { h: "3. Value and redemption", p: [
        "Super Coins have no cash value, are not legal tender, and cannot be sold, transferred, exchanged for cash or combined with another person\u2019s account. One Super Coin is intended to be worth \u20b91 of discount at checkout, once redemption is available for your account. At least \u20b91 of every order must be paid by another payment method. The oldest coins are used first.",
        "Redemption at checkout is subject to availability on the store, and where it is not shown at checkout it is not yet available."] },
      { h: "4. Expiry", p: ["Super Coins you have earned do not expire."] },
      { h: "5. Cancellations and returns", p: ["If you cancel an order or return an item, coins earned on it are reversed or not credited, and coins you used on it are restored to your account in proportion to the refund."] },
      { h: "6. Referral rewards", p: [
        "You may share your referral link or code. When a new customer registers using it and their first order is delivered, the referral is rewarded with **100 Super Coins each** for you and the new customer, in line with the offer shown on the store at that time.",
        "Self-referrals, fake or duplicate accounts, and referrals made through spam or misleading advertising do not qualify. A referred person must be a genuinely new customer."] },
      { h: "7. Misuse", p: ["If we reasonably suspect fraud, manipulation or breach of these terms, we may withhold or cancel coins, reverse rewards and suspend or close the account, after giving you a chance to explain where practicable."] },
      { h: "8. Changes and discontinuation", p: ["We may change the earning rate, redemption rules or programme features, or end the programme, by giving at least 30 days\u2019 notice on the store. Changes do not reduce coins already credited; where redemption is available at the time, you will be given a reasonable chance to use them."] },
      { h: "9. Your data", p: ["We use your purchase, coin and referral data to run the programme, as explained in the [Privacy Policy](/pages/privacy-policy)."] },
      { h: "10. Disputes", p: ["Queries about coins can be raised through My Account or the [Grievance Redressal](/pages/grievance-redressal) page."] },
    ],
  },

  "category-terms": {
    kicker: "PRODUCT CATEGORY CONDITIONS",
    title: "Category-Specific Terms",
    sections: [
      { p: [EFFECTIVE,
        "Some product categories carry extra legal and safety conditions. These apply in addition to our [Terms & Conditions](/pages/terms-and-conditions)."] },
      { h: "Grocery, Fresh Daily and Pet food", p: ["Food items are sold with the batch, manufacture or packing date, expiry or best-before date, and other declarations required by the Food Safety and Standards Act, 2006 and Legal Metrology rules. Our FSSAI licence details are shown on the product page, invoice or the Legal Information page where applicable. Fresh items may vary in size, weight and appearance, and weight may vary slightly for loose items. Please store items as directed. Perishables must be reported within 24 hours of delivery."] },
      { h: "Fashion and Personal Care", p: ["Please check size charts and product details before buying. Colours may vary slightly on screen. For hygiene and safety, opened or used personal care and beauty products and innerwear are not returnable unless damaged, defective or wrong. Cosmetics are sold with batch and expiry details."] },
      { h: "Electronics and Home Appliances", p: ["Products carry the brand\u2019s warranty, where offered. Warranty service is provided by the brand or its authorised service centre. If an item is dead on arrival, report it within 7 days; we may ask for photos or a video of the unboxing and the product. Installation, where needed, is arranged through the brand unless we say otherwise. Please keep the box and invoice."] },
      { h: "Toys & Sports, Gifting and Pooja Essentials", p: ["Check the age rating and safety instructions on toys. Pooja and gifting items are natural or handmade products that may vary in design and finish; we make no claim on religious, spiritual or health outcomes. Gifts can be sent to another address, and the invoice will carry price details unless a gift option is offered."] },
      { h: "Automobiles", p: ["Automobile products are accessories and care products. Please check compatibility with your vehicle before ordering. Items which are fitted incorrectly or used outside the stated purpose are not covered under returns."] },
      { h: "Pharmacy and health products", p: [
        "Medicines and health products are offered only to the extent permitted under the Drugs and Cosmetics Act, 1940 and the rules under it, and only through a valid drug licence held by us or by the licensed pharmacy that supplies the order; the licence details are shown on the relevant page and invoice. Prescription medicines are supplied only against a valid prescription from a registered medical practitioner, which will be verified by a registered pharmacist before dispatch. We do not sell medicines for which the law prohibits online sale.",
        "Information on the Platform is not medical advice; consult a doctor or pharmacist. Once delivered, medicines cannot be returned unless damaged, wrong, expired or defective, and must be reported within 48 hours. Do not use a product if the seal is broken or the expiry has passed."] },
      { h: "Insurance", p: ["Super Bajaar does not issue or underwrite insurance. Insurance information and guidance on the Platform is for general information, and any insurance policy is offered and issued by the insurer or an IRDAI-registered intermediary, under the insurer\u2019s own terms. The premium, benefits, exclusions, claim process and the free-look period are those of the insurer. Insurance is subject to the risk of the subject matter of the cover. Please read the policy document carefully before buying."] },
    ],
  },

  "grievance-redressal": {
    kicker: "CUSTOMER RIGHTS & ESCALATION",
    title: "Grievance Redressal",
    sections: [
      { p: ["We want to put things right quickly. This page sets out how to complain about an order, product, delivery, return, refund, payment, content, your personal data or any service on the Platform, and what you can expect from us."] },
      { h: "Grievance Officer", p: ["**" + BUSINESS.grievanceOfficer + "**, Grievance Officer, " + BUSINESS.entity + "\nEmail: " + BUSINESS.grievanceEmail + "\nPhone / WhatsApp: " + BUSINESS.phone + "\nAddress: " + BUSINESS.address + "\nCustomer support: " + BUSINESS.supportEmail] },
      { h: "How to complain", p: [], ol: [
        "Email the Grievance Officer or call the number above. You can also raise a ticket from My Account.",
        "Include your name, contact details, order number (if any), a clear description of the problem, any photos or documents, and the outcome you want. Do not send passwords, OTPs or card details.",
        "We will give you a complaint reference number. Keep it for follow-up."] },
      { h: "Our timelines", p: ["We will acknowledge your complaint within **48 hours** of receiving it, and redress it within **one month** of receipt. Complaints about personal data will be answered within the time provided by the Digital Personal Data Protection Act, 2023 and its Rules, as they apply."] },
      { h: "Escalation", p: ["If you are not satisfied, you may approach:"], ul: [
        "the **National Consumer Helpline** \u2013 call 1915 or visit [consumerhelpline.gov.in](https://consumerhelpline.gov.in/);",
        "the **Consumer Disputes Redressal Commission** having jurisdiction, including through e-Daakhil;",
        "for personal data matters, the **Data Protection Board of India**, once that mechanism is in force."] },
      { h: "Content takedown", p: ["To report unlawful or infringing content on the Platform, write to the Grievance Officer with the web address of the content, the reason it is unlawful or infringing, and your contact details. We will act on valid notices within the time required by the Information Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021."] },
    ],
  },

  "legal": {
    kicker: "BUSINESS & LEGAL DISCLOSURES",
    title: "Legal Information",
    sections: [
      { p: ["This page gives the business and legal details of Super Bajaar and links to all our policies."] },
      { h: "Seller and business details", p: [], table: { head: ["Detail", "Information"], rows: [
        ["Brand", "Super Bajaar"],
        ["Operated by", "KPMC Enterprises"],
        ["Constitution", "Proprietorship concern"],
        ["Udyam Registration No.", BUSINESS.udyam + " (registered 23 February 2024)"],
        ["Enterprise category and activity", "Micro enterprise \u00b7 Trading"],
        ["Business commenced", "14 November 2021"],
        ["Registered office", BUSINESS.address],
        ["Customer support", BUSINESS.supportEmail + " \u00b7 " + BUSINESS.phone],
        ["Grievance Officer", BUSINESS.grievanceOfficer + " \u00b7 " + BUSINESS.grievanceEmail],
        ["Tax and licence details", "Not currently registered under GST (turnover below the registration threshold). FSSAI and, for pharmacy products, drug licence numbers are shown on invoices and relevant product pages as applicable"],
      ] } },
      { h: "Our policies", p: [], ul: [
        "[Terms & Conditions](/pages/terms-and-conditions)",
        "[Privacy Policy](/pages/privacy-policy) and [Cookie Policy](/pages/cookie-policy)",
        "[Payment Terms](/pages/payment-information)",
        "[Shipping & Delivery Policy](/pages/shipping-delivery)",
        "[Cancellation Policy](/pages/cancellation-policy) and [Returns & Refunds Policy](/pages/returns-refunds)",
        "[Super Coins & Referral Terms](/pages/loyalty-terms)",
        "[Category-Specific Terms](/pages/category-terms)",
        "[Grievance Redressal](/pages/grievance-redressal)"] },
      { h: "Laws we follow", p: ["Our business operates under Indian law, including the Consumer Protection Act, 2019 and the Consumer Protection (E-Commerce) Rules, 2020 (as amended), the Information Technology Act, 2000 and its rules, the Digital Personal Data Protection Act, 2023 and its Rules, the Legal Metrology Act, 2009 and the Packaged Commodities Rules, 2011, the Sale of Goods Act, 1930, the Indian Contract Act, 1872, the applicable tax laws, the Food Safety and Standards Act, 2006 and, for pharmacy products, the Drugs and Cosmetics Act, 1940. We update our policies as these laws change."] },
      { h: "Intellectual property", p: ["The Super Bajaar name, logo and content belong to KPMC Enterprises. Third-party brand names belong to their owners. Please see Section 12 of the [Terms & Conditions](/pages/terms-and-conditions)."] },
      { h: "Official references", p: [], ul: [
        "[Department of Consumer Affairs](https://consumeraffairs.gov.in/)",
        "[National Consumer Helpline](https://consumerhelpline.gov.in/)",
        "[MeitY \u2013 Acts and Policies](https://www.meity.gov.in/documents/act-and-policies)"] },
    ],
  },
};

export const LEGAL_SLUGS = Object.keys(LEGAL_PAGES);
