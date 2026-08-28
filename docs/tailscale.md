# Tailscale — varen oddaljen dostop do dashboarda (PC kot centralni server)

## Namembnost

Dashboard :8787 in proxy :4010 delujeta lokalno na tem PC. Za **varen dostop
od koder koli** (laptop doma / izven, telefon) NE odpiraj javnega porta — ta
dashboard **ni avtenticiran** (CORS `*`). Namesto tega uporabi **Tailscale**,
ki ustvari zasebno, šifrirano omrežje med tvojimi napravami. Zunanji svet ne
vidi nič; samo tvoje naprave (v isti tailnet).

## Stanje na tem sistemu (preverjeno — DELUJE)

- **Tailscale nameščen in povezan** (installer: `https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe`).
- Ta PC (server): **`desktop-a6hvo7u`** · Tailnet IP **`100.93.17.4`** (`tailscale ip -4`).
- Dashboard dosegljiv prek tailnet IP: **`http://100.93.17.4:8787/command` → HTTP 200** ✓
- Druga naprava v tailnetu: **`pcrlprogntb`** · `100.125.242.115` — dosegljiva
  (`tailscale ping 100.125.242.115` → `pong … in ~6ms`).
- Obe napravi pod računom `rob.istria@`.
- Vzpostavljeno tako, da se v zagnanem **Tailscale GUI** (tailscale-ipn.exe)
  potrdi/Connect (in po potrebi `tailscale up` v PowerShell).

## Prva namestitev + `tailscale up` (na novem stroju)

### 1. Namestitev

```powershell
# Najenostavneje: prenesi installer in ga zaženi (potrdi UAC).
# https://tailscale.com/download/windows
# ali neposredno:
Invoke-WebRequest -Uri "https://pkgs.tailscale.com/stable/tailscale-setup-latest.exe" -OutFile "$env:TEMP\tailscale-setup.exe"
Start-Process "$env:TEMP\tailscale-setup.exe"
```

Po namestitvi je `tailscale.exe` v `C:\Program Files\Tailscale\`.

### 2. Avtorizacija

```powershell
tailscale up
```

- Prvič vrne **avtorizacijski URL** (npr. `https://login.tailscale.com/a/xxxx`).
- Odpri URL v brskalniku, prijavi se z **istim računom** (`rob.istria@`) in odobri.
- Po tem `tailscale status` pokaže `Self` kot online.

### 3. Preverba

```powershell
tailscale status        # Self = ta PC, zraven druge naprave v tailnetu
tailscale ip -4         # npr. 100.93.17.4 (tunel vzpostavljen)
tailscale ping <ip>     # ping druge naprave (npr. 100.125.242.115)
```

### Diagnoza, če je "Logged out" / "Unable to connect to coordination server"

- Daemon je nameščen, a ni avtoriziran → `tailscale status` reče `Logged out`
  in izpiše login URL. Odpri ga in odobri, nato ponovi `tailscale up`.
- Če je `NoState` / "Tailscale is starting", počakaj nekaj sekund in ponovi
  `tailscale status`.

## Kako dosežeš dashboard prek omrežja

### 1. Preveri, da je daemon zares »up«

```powershell
tailscale status        # prikaže Self + druge naprave
tailscale ip -4         # 100.93.17.4 (daemon up → IP prisoten)
```

### 2. Odpri dashboard prek tailnet IP

```text
http://100.93.17.4:8787/command
```

Ta naslov je dosegljiv **samo s tvojih naprav v tailnetu** — varno za javni
dostop izven doma. Iz druge naprave odpri ta isti URL.

### 3. Dostop iz drugih naprav

1. Na laptopu/telefonu namesti **Tailscale** in se prijavi z **istim računom**
   (`rob.istria@gmail.com`).
2. Ko so vse naprave v istem tailnetu, odprite `http://100.93.17.4:8787/command`
   z katere koli naprave.

## Uporaben CLI

```powershell
tailscale up            # vzpostavi tunel (prvič: avtorizacija v brskalniku)
tailscale down          # ustavi tunel (lokalno še dela)
tailscale status        # seznam naprav v tailnetu
tailscale ping <ip>     # preveri povezavo do druge naprave
tailscale ip -4         # self IPv4 (tailnet)
tailscale version       # verzija
```

## Integracija s sistemom

- `core/dev_cli.py --serve` ob zagonu preveri `tailscale` na PATH in izpiše
  namig za remote dostop. Če ni nameščen → opozori, lokalni dashboard še dela.
- Dashboard ob poslušanju na `0.0.0.0:8787` je dosegljiv prek LAN IP
  (`http://192.168.0.9:8787`, samo v isti mreži) in prek Tailscale IP
  (`http://100.93.17.4:8787`, kjer koli).

## Varnost — ključno

- **Nikoli ne odpiraj javnega porta 8787/4010** na internet (Firewall/NAT).
- Dashboard nima prijave — **uporabi Tailscale** (zaprto) in ne odprtega porta.
- `client_secret.json` in `.gtoken.json` so v `.gitignore` — ne commit-aj.
