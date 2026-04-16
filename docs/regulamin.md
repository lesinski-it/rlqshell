# Regulamin korzystania z aplikacji RLQShell

**Wersja:** 1.0  
**Data obowiązywania:** 2026-04-16  
**Autor i udostępniający:** Rafał Lesiński

---

## 1. Postanowienia ogólne

1.1. Niniejszy Regulamin określa zasady korzystania z aplikacji **RLQShell** — darmowego, otwartego oprogramowania służącego do zarządzania połączeniami SSH, RDP, VNC, Telnet i Serial oraz do bezpiecznego przechowywania i synchronizacji konfiguracji połączeń.

1.2. Aplikacja RLQShell jest udostępniana bezpłatnie jako oprogramowanie open-source na licencji MIT. Kod źródłowy dostępny jest publicznie w repozytorium projektu.

1.3. Korzystanie z aplikacji oznacza akceptację niniejszego Regulaminu.

1.4. Udostępniającym aplikację jest **Rafał Lesiński** (dalej: „Autor"), osoba fizyczna, będąca autorem projektu.

---

## 2. Opis aplikacji

2.1. RLQShell jest aplikacją desktopową działającą lokalnie na urządzeniu użytkownika. Obsługuje systemy operacyjne Linux, Windows i macOS.

2.2. Aplikacja umożliwia:
- zarządzanie połączeniami SSH, RDP, VNC, Telnet i Serial,
- przeglądanie plików zdalnych przez SFTP,
- przechowywanie sekretów (haseł, kluczy SSH) w lokalnym sejfie,
- synchronizację zaszyfrowanej konfiguracji z własną chmurą użytkownika (Google Drive, OneDrive, Dropbox),
- zarządzanie tunelami portowymi i fragmentami poleceń (Snippets).

2.3. Wszelkie dane konfiguracyjne, hasła i klucze są szyfrowane lokalnie algorytmem AES-256 (Fernet) i chronione hasłem głównym ustalonym przez użytkownika. Autor nie ma do nich dostępu.

---

## 3. Warunki korzystania

3.1. Aplikacja przeznaczona jest dla osób fizycznych i podmiotów korzystających z niej do autoryzowanych celów — administracji systemami, programowania i zarządzania infrastrukturą IT.

3.2. Użytkownik zobowiązuje się:
- korzystać z aplikacji zgodnie z obowiązującym prawem,
- nie używać aplikacji do nawiązywania połączeń z systemami, do których nie posiada uprawnień,
- chronić hasło główne i nie udostępniać go osobom trzecim,
- zachować poufność danych przechowywanych w aplikacji.

3.3. Zabronione jest:
- wykorzystywanie aplikacji do celów niezgodnych z prawem,
- podejmowanie prób obejścia mechanizmów szyfrowania w celu kradzieży danych innych użytkowników,
- dystrybucja zmodyfikowanych wersji aplikacji pod tą samą nazwą bez wyraźnego oznaczenia modyfikacji, o ile ma to na celu wprowadzenie użytkowników w błąd.

---

## 4. Synchronizacja z chmurą

4.1. Funkcja synchronizacji jest opcjonalna i w całości realizowana między urządzeniem użytkownika a jego własnym kontem chmurowym (Google Drive, OneDrive lub Dropbox).

4.2. Autor nie jest pośrednikiem w tej komunikacji, nie ma dostępu do synchronizowanych danych i nie przechowuje ich na żadnych swoich serwerach.

4.3. Dane synchronizowane są wyłącznie w postaci zaszyfrowanej. Klucze szyfrowania są pochodną hasła głównego użytkownika i nigdy nie są przesyłane poza urządzenie.

4.4. Korzystanie z usług chmurowych podlega odrębnym regulaminom dostawców tych usług (Google, Microsoft, Dropbox). Użytkownik jest odpowiedzialny za zapoznanie się z tymi regulaminami.

---

## 5. Odpowiedzialność

5.1. Aplikacja udostępniana jest w stanie „takim jaka jest" (ang. *as is*), bez jakichkolwiek gwarancji działania, dostępności ani przydatności do określonego celu.

5.2. Autor nie ponosi odpowiedzialności za:
- utratę danych spowodowaną błędem użytkownika, awarią sprzętu lub oprogramowania,
- skutki zapomnienia lub utraty hasła głównego (nie istnieje mechanizm odzyskiwania),
- przerwy w działaniu usług chmurowych dostawców zewnętrznych,
- szkody wynikające z nieautoryzowanego dostępu do konta chmurowego użytkownika,
- bezpośrednie lub pośrednie szkody wynikające z korzystania lub niemożności korzystania z aplikacji.

5.3. W maksymalnym zakresie dopuszczalnym przez prawo odpowiedzialność Autora jest wyłączona.

---

## 6. Własność intelektualna

6.1. Kod źródłowy aplikacji RLQShell objęty jest licencją MIT. Pełna treść licencji dostępna jest w pliku `LICENSE` w repozytorium projektu.

6.2. Nazwa „RLQShell" oraz logotyp aplikacji stanowią oznaczenia projektu i mogą być używane w zgodzie z zasadami licencji open-source.

---

## 7. Zmiany Regulaminu

7.1. Autor zastrzega sobie prawo do zmiany niniejszego Regulaminu. Zmiany publikowane są w repozytorium projektu wraz z nową datą obowiązywania.

7.2. Dalsze korzystanie z aplikacji po dacie wejścia w życie zmian oznacza ich akceptację.

---

## 8. Prawo właściwe

8.1. Niniejszy Regulamin podlega prawu polskiemu.

8.2. Wszelkie spory wynikające z korzystania z aplikacji będą rozstrzygane przez sądy właściwe dla miejsca zamieszkania Autora.

---

## 9. Kontakt

W sprawach dotyczących aplikacji można kontaktować się poprzez system zgłoszeń (Issues) w repozytorium projektu lub drogą elektroniczną wskazaną w profilu autora na platformie hostingowej kodu.

---

*Rafał Lesiński — Autor projektu RLQShell*
