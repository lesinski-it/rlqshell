# Polityka Prywatności RLQShell

**Wersja:** 1.0  
**Data obowiązywania:** 2026-04-16  
**Administrator danych:** Rafał Lesiński

---

## 1. Informacje ogólne

1.1. Niniejsza Polityka Prywatności opisuje sposób, w jaki aplikacja **RLQShell** przetwarza (lub — co ważniejsze — nie przetwarza) dane osobowe i dane użytkownika.

1.2. RLQShell jest aplikacją działającą wyłącznie lokalnie. Autor aplikacji, Rafał Lesiński, **nie zbiera, nie przetwarza ani nie przechowuje żadnych danych użytkowników** na własnych serwerach ani w żadnych zewnętrznych usługach administrowanych przez Autora.

1.3. Polityka prywatności sporządzona jest zgodnie z:
- Rozporządzeniem Parlamentu Europejskiego i Rady (UE) 2016/679 (RODO/GDPR),
- Ustawą z dnia 10 maja 2018 r. o ochronie danych osobowych (Dz.U. 2019 poz. 1781).

---

## 2. Jakie dane przetwarza aplikacja?

### 2.1. Dane przechowywane lokalnie

Aplikacja przechowuje na urządzeniu użytkownika wyłącznie dane, które użytkownik sam wprowadził:
- dane konfiguracyjne połączeń (nazwa hosta, adres IP, port, nazwa użytkownika),
- hasła do połączeń i hasła SSH,
- klucze prywatne SSH,
- fragmenty poleceń (Snippets),
- reguły tunelowania portów.

Wszystkie te dane są szyfrowane algorytmem **AES-256 (Fernet)** i chronione **hasłem głównym** ustalonym przez użytkownika. Bez znajomości hasła głównego danych tych nie można odczytać.

### 2.2. Dane synchronizowane z chmurą (opcjonalnie)

Jeśli użytkownik włączy synchronizację z chmurą, zaszyfrowane pliki konfiguracyjne są przesyłane do jego **własnego** konta chmurowego (Google Drive, OneDrive lub Dropbox). Transmisja ta:
- jest w całości inicjowana przez użytkownika,
- odbywa się bezpośrednio między aplikacją a kontem chmurowym użytkownika,
- nie przechodzi przez żadne serwery Autora,
- dotyczy wyłącznie plików zaszyfrowanych — Autor nie ma możliwości ich odczytania.

### 2.3. Dane, których aplikacja nie zbiera

Aplikacja **nie zbiera** żadnych z poniższych danych:
- danych telemetrycznych ani statystyk użycia,
- raportów o błędach (crash reports) wysyłanych do Autora,
- adresów IP użytkowników,
- danych o urządzeniu lub systemie operacyjnym,
- danych geolokalizacyjnych,
- danych identyfikacyjnych (imię, nazwisko, adres e-mail, numer telefonu),
- żadnych innych danych osobowych.

---

## 3. Podstawy prawne przetwarzania

Ponieważ Autor nie przetwarza żadnych danych użytkowników, przepisy RODO dotyczące podstaw prawnych przetwarzania nie mają zastosowania do działalności Autora jako podmiotu.

Dane przechowywane lokalnie na urządzeniu użytkownika przetwarzane są wyłącznie przez samego użytkownika — na jego własne potrzeby i na jego własną odpowiedzialność.

---

## 4. Usługi chmurowe podmiotów trzecich

Jeśli użytkownik korzysta z synchronizacji chmurowej, dane przesyłane do usług Google Drive, OneDrive lub Dropbox podlegają polityce prywatności tych dostawców:

- **Google Drive:** [https://policies.google.com/privacy](https://policies.google.com/privacy)
- **Microsoft OneDrive:** [https://privacy.microsoft.com/pl-pl/privacystatement](https://privacy.microsoft.com/pl-pl/privacystatement)
- **Dropbox:** [https://www.dropbox.com/privacy](https://www.dropbox.com/privacy)

Użytkownik jest odpowiedzialny za zapoznanie się z politykami prywatności tych dostawców.

---

## 5. Bezpieczeństwo danych

5.1. **Szyfrowanie lokalne:** wszystkie wrażliwe dane (hasła, klucze, konfiguracje) są szyfrowane algorytmem AES-256 (Fernet) przed zapisem na dysk.

5.2. **Hasło główne:** klucz szyfrowania jest pochodną hasła głównego użytkownika. Hasło główne nigdy nie jest zapisywane w postaci jawnej ani przesyłane gdziekolwiek.

5.3. **Brak centralnego serwera:** Autor nie prowadzi żadnego serwera, który mógłby stać się celem ataku w celu uzyskania danych użytkowników.

5.4. **Odpowiedzialność użytkownika:** bezpieczeństwo danych zależy od siły hasła głównego oraz od zabezpieczenia własnego konta chmurowego. W przypadku utraty hasła głównego odzyskanie danych jest niemożliwe.

---

## 6. Prawa użytkownika (RODO)

Ponieważ Autor nie przetwarza żadnych danych osobowych użytkowników, prawa wynikające z RODO (prawo dostępu, sprostowania, usunięcia, przenoszenia, sprzeciwu) dotyczą wyłącznie danych przechowywanych lokalnie na urządzeniu użytkownika — użytkownik może nimi zarządzać bezpośrednio w aplikacji lub usuwając jej dane.

---

## 7. Pliki cookie i śledzenie

Aplikacja RLQShell jest aplikacją desktopową. Nie używa plików cookie, nie stosuje skryptów śledzących ani żadnych innych mechanizmów identyfikacji stosowanych w środowiskach webowych.

---

## 8. Zmiany Polityki Prywatności

8.1. Autor zastrzega sobie prawo do zmiany niniejszej Polityki Prywatności. Zmiany są publikowane w repozytorium projektu z nową datą obowiązywania.

8.2. Dalsze korzystanie z aplikacji po wejściu w życie zmian oznacza ich akceptację.

---

## 9. Kontakt

W sprawach dotyczących prywatności i ochrony danych można kontaktować się za pośrednictwem systemu zgłoszeń (Issues) w repozytorium projektu lub drogą elektroniczną wskazaną w profilu Autora na platformie hostingowej kodu.

---

*Rafał Lesiński — Autor projektu RLQShell*
