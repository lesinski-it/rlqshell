# Build RLQShell na Debian/Ubuntu/Pop!_OS/Mint

Ponizsze kroki tworza pakiet `.deb` z launcherem aplikacji i wpisem w menu systemowym.

## 1. Zainstaluj wymagania systemowe

```bash
sudo apt update
sudo apt install -y \
  python3 python3-venv python3-pip \
  build-essential \
  dpkg-dev
```

## 2. Przygotuj srodowisko Python

```bash
cd /sciezka/do/TermPlus
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Jesli uzywasz Pythona 3.14+, ustaw przed `pip install`:

```bash
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1
```

## 3. Zbuduj pakiet `.deb`

```bash
chmod +x installer/build-deb.sh
bash installer/build-deb.sh
```

Gotowy pakiet pojawi sie w:

```text
dist/rlqshell_<wersja>_<architektura>.deb
```

Przyklad: `dist/rlqshell_0.1.0_amd64.deb`

## 4. Instalacja pakietu

```bash
sudo apt install ./dist/rlqshell_0.1.0_amd64.deb
```

Po instalacji:
- komenda CLI: `rlqshell`
- plik binarny: `/opt/rlqshell/RLQShell`
- launcher GUI: menu aplikacji (`RLQShell`)

## Opcje skryptu

```bash
bash installer/build-deb.sh --help
```

Najwazniejsze:
- `--version <x.y.z>`: nadpisuje wersje z `pyproject.toml`
- `--arch <arch>`: nadpisuje architekture (domyslnie `dpkg --print-architecture`)
- `--skip-pyinstaller`: pakuje istniejacy `dist/RLQShell` bez ponownego buildu
