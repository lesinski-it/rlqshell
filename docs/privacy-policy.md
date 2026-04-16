# Privacy Policy for RLQShell

**Version:** 1.0  
**Effective date:** 2026-04-16  
**Data controller:** Rafał Lesiński

---

## 1. General information

1.1. This Privacy Policy describes how the **RLQShell** application processes — or, more importantly, does not process — personal and user data.

1.2. RLQShell runs entirely on your local device. The Author of the application, Rafał Lesiński, **does not collect, process, or store any user data** on his own servers or in any external services administered by the Author.

1.3. This Privacy Policy is drawn up in accordance with:
- Regulation (EU) 2016/679 of the European Parliament and of the Council (GDPR),
- the Polish Act of 10 May 2018 on the Protection of Personal Data.

---

## 2. What data does the application process?

### 2.1. Data stored locally

The application stores on your device only the data that you have entered yourself:
- connection configuration data (hostname, IP address, port, username),
- connection passwords and SSH passwords,
- SSH private keys,
- command snippets,
- port-forwarding rules.

All of this data is encrypted using **AES-256 (Fernet)** and protected by the **master password** you set. The data cannot be read without knowledge of the master password.

### 2.2. Data synchronised to the cloud (optional)

If you enable cloud synchronisation, encrypted configuration files are transferred to **your own** cloud account (Google Drive, OneDrive, or Dropbox). This transfer:
- is initiated entirely by you,
- occurs directly between the application and your cloud account,
- does not pass through any servers controlled by the Author,
- involves only encrypted files — the Author has no means of reading them.

### 2.3. Data the application does not collect

The application **does not collect** any of the following:
- telemetry data or usage statistics,
- crash reports sent to the Author,
- users' IP addresses,
- device or operating-system information,
- geolocation data,
- identifying information (name, e-mail address, phone number),
- any other personal data.

---

## 3. Legal bases for processing

Because the Author does not process any user data, the GDPR provisions regarding legal bases for processing do not apply to the Author as a data-processing entity.

Data stored locally on your device is processed solely by you — for your own purposes and at your own responsibility.

---

## 4. Third-party cloud services

If you use the cloud synchronisation feature, data transmitted to Google Drive, OneDrive, or Dropbox is subject to those providers' privacy policies:

- **Google Drive:** [https://policies.google.com/privacy](https://policies.google.com/privacy)
- **Microsoft OneDrive:** [https://privacy.microsoft.com/en-us/privacystatement](https://privacy.microsoft.com/en-us/privacystatement)
- **Dropbox:** [https://www.dropbox.com/privacy](https://www.dropbox.com/privacy)

You are responsible for reviewing and complying with the privacy policies of those providers.

---

## 5. Data security

5.1. **Local encryption:** all sensitive data (passwords, keys, configurations) is encrypted with AES-256 (Fernet) before being written to disk.

5.2. **Master password:** the encryption key is derived from your master password. The master password is never stored in plain text or transmitted anywhere.

5.3. **No central server:** the Author does not operate any server that could be targeted by an attack to obtain user data.

5.4. **User responsibility:** the security of your data depends on the strength of your master password and on how well you secure your cloud account. If the master password is lost, data recovery is not possible.

---

## 6. Your rights under the GDPR

Because the Author does not process any users' personal data, the GDPR rights (right of access, rectification, erasure, portability, and objection) apply exclusively to data stored locally on your device. You can manage that data directly within the application or by deleting its local files.

---

## 7. Cookies and tracking

RLQShell is a desktop application. It does not use cookies, tracking scripts, or any other identification mechanisms used in web environments.

---

## 8. Changes to this Privacy Policy

8.1. The Author reserves the right to amend this Privacy Policy. Changes are published in the project repository with a new effective date.

8.2. Continued use of the application after the effective date of any changes constitutes your acceptance of those changes.

---

## 9. Contact

For matters relating to privacy and data protection, please use the issue tracker in the project repository or the electronic contact indicated in the Author's profile on the code hosting platform.

---

*Rafał Lesiński — Author of the RLQShell project*
