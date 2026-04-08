Ready for review
Select text to add comments on the plan
Strategia komercjalizacji RLQShell — wycena i model przychodów
Kontekst
Stan obecny (na 2026-04-07):

Aplikacja: [RLQShell](d:/Projekty programistyczne/TermPlus/) — modern cross-platform SSH client (PySide6/paramiko), klon Termiusa z USP "private cloud sync"
Wersja: 0.1.0 (alpha) wg [pyproject.toml:7](d:/Projekty programistyczne/TermPlus/pyproject.toml#L7)
Licencja: MIT wg [LICENSE:1](d:/Projekty programistyczne/TermPlus/LICENSE#L1) i [pyproject.toml:10](d:/Projekty programistyczne/TermPlus/pyproject.toml#L10)
Motto wg [docs/rlqshell-spec.md:25](d:/Projekty programistyczne/TermPlus/docs/rlqshell-spec.md#L25): „Twoje klucze. Twoja chmura. Zero subskrypcji."
Funkcje: SSH/RDP/VNC/Telnet/Serial, SFTP, Vaults, Snippets, Keychain, Port Forwarding, Command Palette, multi-cloud sync (Google Drive/Dropbox/OneDrive)
MSI installer + pipeline release już istnieje (commit 38beccf)
Twoje warunki brzegowe (z odpowiedzi):

Solo dev, kod jeszcze nie jest publiczny → pełna swoboda licencyjna
Cel: B2C globalnie (pojedynczy developerzy/admini)
Mały budżet: code-signing cert, domena, Stripe (~500–1000 EUR/rok)
Chcesz maksymalizować przychód
Konkurencja na rynku B2C SSH clients:

Produkt	Model	Cena	Pozycja
Termius	SaaS subskrypcja	~$80/rok Pro	Lider B2C, ale wszyscy hate'ują subskrypcję
MobaXterm	Pay-once (Windows-only)	$69 Personal	Stary, brzydki UI, ale zarabia
Sublime Text (porównanie modelu)	Pay-once + 3y updates	$99	Indie B2C złoty standard
Tabby	Free OSS	0	Brak monetyzacji
WindTerm	Free + donacje	0	Brak monetyzacji
Putty	Free	0	Legacy
Główne obserwacje:

Twoje USP ("private cloud, zero subskrypcji") jest bezpośrednio wymierzone w największą słabość Termiusa — to jest dobre pozycjonowanie
Jeśli złamiesz motto i wprowadzisz subskrypcję, tracisz przewagę nad Termiusem i zostajesz "tańszą kopią lidera". Nie warto.
B2C indie dev tools z pay-once + windowed updates (Sublime, JetBrains personal, Beyond Compare) to sprawdzony model dla solo devów
Decyzja strategiczna: pay-once z 12-miesięcznym oknem updates + Open Core
Model: Otwarty rdzeń (MIT) + zamknięty Pro (proprietary binary), pay-once z perpetual fallback license.

Dlaczego nie subskrypcja:

Łamie motto = tracisz USP vs Termius
B2C indie tools mają wysoki churn (~30-50%/rok), MRR wygląda dobrze tylko na papierze
Wymaga ciągłego płacenia za infra (auth, billing, license server) = większy stały koszt
Pay-once + Stripe Checkout = jeden plik konfiguracyjny i koniec
Dlaczego Open Core, a nie pełne closed-source:

Free tier OSS napędza wirality (HN, Reddit, GitHub stars) — kluczowe dla B2C bez budżetu marketingowego
Spec mówi explicite "open-source" jako element USP — łamanie tego = utrata części wczesnych adopterów
Pro features w osobnym (zamkniętym) repo = automatyczna ochrona, nie trzeba CLA
Możesz bez wstydu mówić "open source SSH client z premium features"
Tiery i wycena
Tier 1: RLQShell Community — 0 EUR
Licencja: MIT (pełne źródła publiczne, można buildować samemu)

Funkcje:

Wszystkie protokoły: SSH, RDP, VNC, Telnet, Serial
Lokalny vault szyfrowany (Fernet/AES-256)
Lokalny SFTP, Port Forwarding, Snippets, Keychain
Command Palette, themes (4 palety: cyan/emerald/amber/azure)
Sync TYLKO do jednego wybranego backendu (np. tylko lokalny folder lub tylko Google Drive)
Brak signed binaries — użytkownik buduje z PyInstaller sam, lub pobiera unsigned z GitHub
Cel: Wirality, audience, reputation, GitHub stars, recenzje

Tier 2: RLQShell Pro — 39 EUR (one-time)
Licencja: Proprietary (closed binary), perpetual use, 12 miesięcy updates

Co dostaje (ponad Community):

Wszystkie cloud backendy jednocześnie: Google Drive + Dropbox + OneDrive + Nextcloud + WebDAV
Multi-device sync z conflict resolution i historią zmian (najważniejszy feature płatny)
Signed installers dla Windows (MSI z code-sign) i macOS (notarized) + auto-update
Premium theme packs (np. dodatkowe 8-12 palet, custom terminal color schemes Pro-only)
Premium snippet packs (curated DevOps libraries: Docker/k8s/AWS/git workflows)
Priority bug fixes + bezpośredni email support
12 miesięcy darmowych updates — po tym czasie aplikacja działa wiecznie w ostatniej wersji, ale upgrade na nowsze wersje = 50% ceny (19 EUR)
Cel: Główny silnik przychodu

Tier 3: RLQShell Lifetime — 99 EUR (one-time)
Wszystko z Pro plus:

Lifetime updates na zawsze
Wczesny dostęp do nowych funkcji (beta channel)
Opcjonalny wpis na stronę "supporters"
Symboliczne podziękowanie w About (opt-in)
Cel: Superfans, wczesny cashflow, "build in public" momentum

Wczesny launch: early-bird discount
Pierwszych 100 sprzedaży: Pro 19 EUR / Lifetime 49 EUR
Następnych 400: Pro 29 EUR / Lifetime 69 EUR
Po 500 sprzedażach: ceny full (39 / 99)
Komunikacja: "ceny rosną przy każdym kamieniu milowym" → urgency bez sztucznych deadlines
Argumentacja cenowa:

19 EUR (early bird Pro) = impulsywny zakup, nie wymaga zatwierdzenia
39 EUR Pro = sweet spot dla indie tools
99 EUR Lifetime = "kocham ten tool, biorę na zawsze"
W sumie poniżej rocznego Termiusa Pro ($80) = łatwa argumentacja "kup raz, zapomnij"
Architektura kodu i licencji (technicznie)
Dwa repozytoria:

rlqshell (publiczny, MIT):

Cały obecny kod minus Pro features
Buildowalny do pełnej Community edition
Hostowany na GitHub (lub Gitea jeśli już używasz)
rlqshell-pro (prywatny, proprietary):

Plugin layer ładowany w runtime przez rlqshell.core.plugin_loader ([istniejący już w spec](d:/Projekty programistyczne/TermPlus/docs/rlqshell-spec.md))
Zawiera: multi-cloud sync engine, conflict resolution, premium themes, premium snippet packs, license verification
Builduje finalne signed instalatory zawierające oba kody
Na ten moment pusty placeholder — można dodawać Pro features iteracyjnie
Zmiany w kodzie wymagane na start:

Dodać core/license.py — weryfikacja klucza licencji (offline JWT signed Twoim kluczem prywatnym)
Dodać core/plugin_loader.py hook do ładowania rlqshell_pro jeśli zainstalowany
W [docs/rlqshell-spec.md](d:/Projekty programistyczne/TermPlus/docs/rlqshell-spec.md) zaznaczyć które features są Pro
W Settings dodać "Activate License" dialog
Zostawić MIT w głównym repo — to jest celowe
Konkretna lista action items (kolejność wykonania)
Faza 1: Fundamenty prawne i brand (~200 EUR, 2-3 tyg.)
Wybrać i kupić domenę (np. rlqshell.io, rlqshell.dev) — ~15 EUR/rok
Zarejestrować konto Stripe + sole proprietorship w Polsce (jeśli jeszcze nie masz, działalność nierejestrowana to ~3.5k PLN/mc limit, na początek wystarczy)
EULA + Privacy Policy dla Pro — wystarczy template z iubenda.com lub własny
Zdecydować nazwę handlową — sprawdź wolność znaku w EUIPO (sprawdzenie darmowe)
Decision: czy wnosić zgłoszenie znaku towarowego "RLQShell" w EUIPO (~850 EUR za 1 klasę, opcjonalne na start)
Faza 2: Infrastruktura sprzedaży (~500 EUR jednorazowo + ~50 EUR/mc, 2-4 tyg.)
Code signing certificate:
Windows: SSL.com lub Sectigo OV cert ~250 EUR/rok (EV cert ~500 EUR/rok = brak SmartScreen warningów)
macOS: Apple Developer Program ~100 EUR/rok (notarization included)
Strona WWW — statyczna (Astro/11ty/Hugo), hosting Cloudflare Pages (free), 1 strona głównej + 1 strona pricing + 1 strona docs
Stripe Checkout — embed na stronie, webhook do generowania licencji
License key generator — prosty Python skrypt podpisujący JWT Twoim Ed25519 keyem (offline, nie potrzeba serwera)
Email: prosty postbox/Fastmail (~50 EUR/rok) + Resend/Postmark do transactional emails
Faza 3: Kod — separacja Pro features (4-8 tyg. solo dev)
Stworzyć prywatne repo rlqshell-pro
Przenieść wieloplatformowe sync backendy do rlqshell-pro/sync/ — w community zostaje TYLKO single backend
Zaimplementować core/license.py (weryfikacja JWT offline)
Zaimplementować plugin_loader.py hook
Zbudować pierwszą wersję Pro: signed MSI dla Windows + auto-updater
Zaktualizować [docs/rlqshell-spec.md](d:/Projekty programistyczne/TermPlus/docs/rlqshell-spec.md) — sekcja "Editions: Community vs Pro"
Faza 4: Launch i marketing (ciągle, ~200 EUR)
Build in public — Twitter/Mastodon thread o postępach 1-2x w tygodniu
HN launch post — "Show HN: RLQShell — open-source SSH client with private cloud sync"
Reddit posts: r/sysadmin, r/selfhosted, r/commandline, r/devops, r/programming
ProductHunt launch — przygotować assets, znaleźć huntera
Lobste.rs, DevTo, Hacker Newsletter sponsoring (1 sponsorship ~150 EUR)
YouTube demo — 3-5 min walkthrough, embed na stronie
Comparison page: "RLQShell vs Termius" (SEO)
GitHub releases z signed binaries Community + linkiem "Get Pro features"
Faza 5: Post-launch optymalizacja (ciągle)
Trackuj conversion rate Community → Pro (cel: 1-3%)
Eksperymentuj z A/B testem cen (39 vs 49 vs 29)
Zbieraj feedback od pierwszych klientów — jakie features dodać do Pro
Po ~6 miesiącach rozważ Team tier jeśli enterprise wpadnie organicznie
Realistyczne projekcje przychodu (B2C indie SSH client, solo dev)
Okres	Sprzedaże	Średnia cena	Przychód brutto	Komentarz
Miesiące 1-3	50-150 (early bird)	25 EUR	1.2k–3.7k EUR	HN + Reddit launch boost
Miesiące 4-12	150-400	35 EUR	5k–14k EUR	Word of mouth, SEO
Year 2	400-800	39 EUR	15k–31k EUR	Recenzje, repeat traffic
Year 3+	600-1500	39-50 EUR	23k-75k EUR	Zależy od retention + brandu
Realistyczny scenariusz średni: ~10-20k EUR w roku 1, ~20-40k EUR/rok ustabilizowane.

Pessymistyczny scenariusz: 2-5k EUR/rok (brak trakcji marketingowej).

Optymistyczny: 50k+ EUR/rok jeśli wpadnie viral moment + 1-2 enterprise deale ad-hoc.

Koszty operacyjne roczne: ~800-1200 EUR (cert, domena, hosting, payment processing 2.9% Stripe, transactional emails). Marża netto > 90%.

Czego NIE robić
NIE wprowadzaj subskrypcji — łamie motto, zabija różnicowanie vs Termius
NIE rób free trial Pro — daj Community zamiast tego (lepsze dla wirality)
NIE crippluj Community zbyt mocno — jeśli ludzie nie mogą używać do podstawowej pracy, nikt o nim nie napisze
NIE buduj własnego serwera licencji — JWT offline wystarczy. Mniej infra = mniej kosztów + mniej awarii
NIE celuj w enterprise na start — wymaga sales pipeline którego solo dev nie pociągnie. Enterprise przyjdzie organicznie po year 2 jeśli produkt dobry
NIE inwestuj 800 EUR w EV cert dopóki nie masz pierwszych 100 sprzedaży — zacznij z OV (~250 EUR), użytkownicy klikną przez SmartScreen warning
NIE rób localizacji na start (poza PL/EN) — narzut testów > zysk z dodatkowych rynków
NIE zmieniaj licencji core na AGPL/BUSL — komplikacja prawna, B2C nie rozumie różnicy, MIT na core to dobry signal trustu
Kluczowe pliki i miejsca w repo do modyfikacji
Plik	Zmiana
[pyproject.toml](d:/Projekty programistyczne/TermPlus/pyproject.toml)	Zostawić MIT + dodać optional [project.optional-dependencies] pro = ["rlqshell-pro"]
[docs/rlqshell-spec.md](d:/Projekty programistyczne/TermPlus/docs/rlqshell-spec.md)	Dodać sekcję "§N. Editions: Community vs Pro" + zmienić listę features oznaczając Pro-only
[LICENSE](d:/Projekty programistyczne/TermPlus/LICENSE)	Zostawić MIT (tylko core)
[rlqshell/core/](d:/Projekty programistyczne/TermPlus/rlqshell/core/)	Dodać license.py (JWT offline verification)
[rlqshell/core/plugin_loader.py](d:/Projekty programistyczne/TermPlus/rlqshell/core/)	Hook do ładowania rlqshell_pro jeśli zainstalowany (wg spec już istnieje)
rlqshell/ui/settings/	Dodać "License" panel z aktywacją klucza
installer/	Wariant signed Pro vs unsigned Community
Nowe repo rlqshell-pro (prywatne)	Plugin z multi-cloud sync, premium themes, conflict resolution
Verification — jak zwalidować model przed pełnym launchem
Walidacja popytu PRZED budowaniem Pro:

Wystaw landing page z opisem Pro features i przyciskiem "Notify me at launch — pre-order 19 EUR"
Push przez build-in-public posty
Jeśli zbierzesz <50 emaili w 4 tygodnie — model B2C nie zadziała, rozważ pivot na donacje/usługi
Jeśli 50-200 emaili — kontynuuj zgodnie z planem
Jeśli >200 emaili — możesz podnieść ceny
Walidacja willingness-to-pay:

Po HN launch: poll w komentarzach lub Twitter "co bys zapłacił za Pro version z multi-cloud sync"
Jeśli mediana <20 EUR — obniż Pro na 29 EUR
Jeśli mediana >50 EUR — podnieś Lifetime na 129 EUR
Walidacja conversion:

Po 1000 unique visits na pricing page: jeśli conversion <0.5%, popraw pricing page
Jeśli >2%, dorzuć więcej ruchu (SEO, sponsorshipy)
Smoke test license flow end-to-end:

Symulować zakup w Stripe test mode → webhook → wygenerowanie JWT → email do klienta → aktywacja w aplikacji → Pro features unlock
Refund policy: 30 dni money-back, no questions asked. To zwiększa conversion o 10-20% i kosztuje minimalne refundy.

TL;DR
Model: Open Core (MIT free + proprietary Pro plugin), pay-once z 12-mies. updates window, brak subskrypcji.

Ceny: Community 0 EUR / Pro 39 EUR (early bird 19) / Lifetime 99 EUR (early bird 49).

Główny przychód z: multi-cloud sync, signed installers, auto-update, conflict resolution, premium themes/snippets.

Realistyczny przychód roczny: 10-40k EUR po roku 1-2, marża >90%.

Kluczowa zasada: Nie łamać motto "Zero subskrypcji" — to jest Twoje USP, nie poświęcaj go dla MRR.

Najważniejszy first step: Zwaliduj popyt landing page'em z waitlist PRZED inwestowaniem w cert, repo split i Pro features. Jeśli nikt nie zapisze się na waitlistę, oszczędziłeś sobie miesięcy pracy.