# Terms of Service for RLQShell

**Version:** 1.0  
**Effective date:** 2026-04-16  
**Author and provider:** Rafał Lesiński

---

## 1. General provisions

1.1. These Terms of Service govern the use of **RLQShell** — a free, open-source desktop application for managing SSH, RDP, VNC, Telnet and Serial connections, and for securely storing and synchronising connection configurations.

1.2. RLQShell is provided free of charge as open-source software under the MIT licence. The source code is publicly available in the project repository.

1.3. By using the application, you agree to these Terms of Service.

1.4. The application is provided by **Rafał Lesiński** (hereinafter "the Author"), an individual and the creator of the project.

---

## 2. Description of the application

2.1. RLQShell is a desktop application that runs locally on the user's device. It supports Linux, Windows, and macOS.

2.2. The application allows you to:
- manage SSH, RDP, VNC, Telnet, and Serial connections,
- browse remote files via SFTP,
- store secrets (passwords, SSH keys) in a local encrypted vault,
- synchronise encrypted configuration with your own cloud storage (Google Drive, OneDrive, Dropbox),
- manage port-forwarding tunnels and command snippets.

2.3. All configuration data, passwords, and keys are encrypted locally using AES-256 (Fernet) and protected by a master password set by the user. The Author has no access to this data.

---

## 3. Conditions of use

3.1. The application is intended for individuals and organisations using it for authorised purposes — system administration, software development, and IT infrastructure management.

3.2. You agree to:
- use the application in compliance with applicable laws,
- only connect to systems for which you hold the necessary authorisation,
- protect your master password and not share it with third parties,
- maintain the confidentiality of data stored in the application.

3.3. The following are prohibited:
- using the application for any unlawful purpose,
- attempting to circumvent the encryption mechanisms in order to access another user's data,
- distributing modified versions of the application under the same name without clearly marking the modifications, where such conduct is intended to mislead users.

---

## 4. Cloud synchronisation

4.1. The synchronisation feature is entirely optional and is carried out solely between the user's device and their own cloud account (Google Drive, OneDrive, or Dropbox).

4.2. The Author is not an intermediary in this communication, does not have access to synchronised data, and does not store it on any servers controlled by the Author.

4.3. Data is synchronised only in encrypted form. Encryption keys are derived from the user's master password and are never transmitted outside the device.

4.4. Use of cloud services is subject to the separate terms of service of those providers (Google, Microsoft, Dropbox). You are responsible for reviewing and complying with those terms.

---

## 5. Disclaimer of liability

5.1. The application is provided on an **"as is"** basis, without any warranty of functionality, availability, or fitness for a particular purpose.

5.2. The Author is not liable for:
- loss of data caused by user error, hardware failure, or software failure,
- consequences of forgetting or losing the master password (no recovery mechanism exists),
- interruptions in the services provided by third-party cloud providers,
- damages resulting from unauthorised access to the user's cloud account,
- any direct or indirect damages arising from the use of or inability to use the application.

5.3. To the maximum extent permitted by applicable law, the Author's liability is excluded.

---

## 6. Intellectual property

6.1. The source code of RLQShell is licensed under the MIT Licence. The full text of the licence is available in the `LICENSE` file in the project repository.

6.2. The name "RLQShell" and the application's logo are identifiers of the project and may be used in accordance with the principles of the open-source licence.

---

## 7. Changes to the Terms of Service

7.1. The Author reserves the right to amend these Terms of Service. Changes are published in the project repository together with a new effective date.

7.2. Continued use of the application after the effective date of any changes constitutes your acceptance of those changes.

---

## 8. Governing law

8.1. These Terms of Service are governed by the laws of Poland.

8.2. Any disputes arising from the use of the application shall be subject to the jurisdiction of the courts competent for the Author's place of residence.

---

## 9. Contact

For matters relating to the application, please use the issue tracker in the project repository or the electronic contact indicated in the Author's profile on the code hosting platform.

---

*Rafał Lesiński — Author of the RLQShell project*
