# Tailscale — varen oddaljen dostop do dashboarda (PC kot centralni server)

## Namembnost

Dashboard :8787 in proxy :4010 delujeta lokalno na tem PC. Za **varen dostop
od koder koli** (laptop doma / izven, telefon) NE odpiraj javnega porta — ta
dashboard **ni avtenticiran** (CORS `*`). Namesto tega uporabi **Tailscale**,
ki ustvari zasebno, šifrirano omrežje med tvojimi napravami. Zunanji svet ne
vidi nič; samo tvoje naprave (v isti tailnet).

## Stanje na tem sistemu (preverjeno)

- **Tailscale nameščen** (`tailscaled.exe` teče kot storitev).
- **Prijavljen v tailnet** (`rob.istria@gmail.com`, "Login successful") — to JE
  narejeno; prijava je v redu.
- **Slediti mora še `tailscale up`** — dokler ta korak ni dokončan, je daemon v
  stanju `NoState` / *"Tailscale is starting"* / *"Unable to connect to the
  Tailscale coordination server"*, in **dashboard NI dosegljiv prek tailnet IP**
  (`tailscale ip -4` → "no current Tailscale IPs"). To je NORMALNO takoj po
  prijavi — le treba je vzpostaviti tunel.

## DOKONČAJ `tailscale up` (najprej to)

Ko se prijaviš ("Login successful"), moraš še **vzpostaviti povezavo**:

### Možnost A — prek GUI (najenostavnejše)
1. Odpri **Tailscale** aplikacijo (vseeno se je odprla / ikona na systray).
2. V oknu izberi/najdi gumb **»Connect«** (ali »Up«).
3. Če odpre spletno okno za **avtorizacijo/consent**, ga potrdi.
4. Po tem postane status **"Connected"** in dobiš IP.

### Možnost B — prek CLI (PowerShell, ne Git Bash)
```powershell
tailscale up
```
- Če se odpre URL soglasja, ga odpri in potrdi.
- Po tem preveriš:

```powershell
tailscale status        # Self naj bo "online"
tailscale ip -4         # vrne npr. 100.x.y.z (tunel je vzpostavljen)
```

### Diagnoza, če je "Unable to connect to coordination server"
- Pomeni, da daemon še ni sinhroniziral z Tailscale strežnikom — pogosto samo
  potrdiš `/ dokoletna privolitev v **up** (GUI Connect ali `tailscale up`) in
  počakaš nekaj sekund.
- Preveri z `tailscale status` — ko ni več "starting"/`NoState`, je OK.

## Kako dosežeš dashboard prek omrežja

### 1. Preveri, da je daemon zares »up«

Po `tailscale up` (zgoraj) preveri v PowerShell:

```powershell
tailscale status        # prikaže Self + druge naprave; če "starting", počakaj
tailscale ip -4         # npr. 100.125.242.115 (daemon up → IP prisoten)
```

Če ti `tailscale status` še reče `NoState` / "Tailscale is starting", **še ni
dokončano** — ponovi korak "DOKONČAJ tailscale up" zgoraj in počakaj.

### 2. Odpri dashboard prek tailnet IP

```text
http://<tailscale-IP>:8787
```

Primer (IP iz tega setupa):
```text
http://100.125.242.115:8787
```

Ta naslov je dosegljiv **samo s tvojih naprav v tailnetu** — varno za javni
dostop izven doma.

### 3. Dostop iz drugih naprav

1. Na laptopu/telefonu namesti **Tailscale** in se prijavi z **istim računom**
   (`rob.istria@gmail.com`).
2. Ko so vse naprave v istem tailnetu, odprite `http://<tailscale-IP>:8787`
   z katere koli naprave.

## Uporaben CLI

```powershell
tailscale up            # vzpostavi tunel
tailscale down          # ustavi tunel (lokalno še dela)
tailscale status        # seznam naprav v tailnetu
tailscale ip -4         # self IPv4 (tailnet)
tailscale version       # verzija
```

## Integracija s sistemom

- `core/dev_cli.py --serve` ob zagonu preveri `tailscale` na PATH in izpiše
  namig za remote dostop. Če ni nameščen → opozori, lokalni dashboard še dela.
- Dashboard ob poslušanju na `0.0.0.0:8787` je dosegljiv prek LAN IP
  (`http://192.168.0.9:8787`, samo v isti mreži) in prek Tailscale IP
  (`http://100.x.x.x:8787`, kjer koli).

## Varnost — ključno

- **Nikoli ne odpiraj javnega porta 8787/4010** na internet (Firewall/NAT).
- Dashboard nima prijave — **uporabi Tailscale** (zaprto) in ne odprtega porta.
- `client_secret.json` in `.gtoken.json` so v `.gitignore` — ne commit-aj.
