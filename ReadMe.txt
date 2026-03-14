============================================================
Convert RINEX – Local RINEX 3 → RINEX 2 Converter
============================================================
ROMÂNĂ

DESCRIERE GENERALĂ
Convert RINEX este o aplicație Windows locală (GUI) care automatizează conversia fișierelor RINEX versiunea 3 în RINEX versiunea 2 folosind utilitarul oficial GFZRNX.
Aplicația este concepută pentru fluxuri de lucru GNSS / POSPac / pre-procesare și permite:
-conversie automată
-monitorizare folder (hot folder)
-suport drag & drop
-dezarhivare automată ZIP (inclusiv ZIP în ZIP)
-filtrare automată fișiere observații (_MO.rnx)
-rulare fără consolă (fără CMD vizibil)
-interfață grafică simplă

FUNCȚIONALITĂȚI PRINCIPALE
Conversie RINEX 3 → RINEX 2

Utilizează executabilul GFZRNX pentru conversie automată.
Hot Folder Monitoring
Folderul INBOX_DROP este monitorizat automat.
Orice fișier nou este procesat automat.

Drag & Drop
Utilizatorul poate trage fișiere sau foldere direct în aplicație.

Dezarhivare automată ZIP
Acceptă fișiere .zip
Dezarhivează recursiv (ZIP în ZIP)

Caută automat fișiere .rnx

Filtrare automată
Procesează doar fișierele de observații (ex: *_MO.rnx)
Ignoră fișierele CN / EN / GN / RN.

Organizare automată foldere
INBOX_DROP – fișiere de intrare
OUTBOX_CONVERTED – fișiere convertite
PROCESSED – fișiere deja procesate
ERRORS – fișiere cu erori
LOGS – log-uri execuție

Interfață fără consolă
Aplicația este compilată ca .exe fără fereastră CMD.

FLUX DE LUCRU
Se copiază un ZIP sau un fișier RINEX 3 în INBOX_DROP

Aplicația:
-dezarhivează (dacă este ZIP)
-caută fișierele .rnx
-filtrează doar fișierele relevante
-rulează GFZRNX
-Fișierul convertit este salvat în OUTBOX_CONVERTED
-Fișierul original este mutat în PROCESSED

La final dupa drag & drop CLICK pe Deschide OUTBOX_CONVERTED pentru a ajunge la fisierele convertite

CERINȚE
Windows 10 / 11
gfzrnx_2.2.0_win11_64.exe în același folder cu aplicația
Nu necesită Python instalat dacă se folosește versiunea .exe


ENGLISH

GENERAL DESCRIPTION
Convert RINEX is a local Windows GUI application that automates the conversion of RINEX version 3 files to RINEX version 2 using the official GFZRNX utility.

The application is designed for GNSS / POSPac / pre-processing workflows and provides:
-automatic conversion
-hot-folder monitoring
-drag & drop support
-automatic ZIP extraction (including nested ZIP files)
-automatic observation file filtering (_MO.rnx)
-no visible console window
-simple graphical interface

MAIN FEATURES
RINEX 3 → RINEX 2 Conversion
Uses GFZRNX executable for automatic conversion.

Hot Folder Monitoring
INBOX_DROP folder is automatically monitored.
Any new file is processed automatically.

Drag & Drop
Users can drag files or folders directly into the application.

Automatic ZIP Extraction
Supports .zip archives
Recursive extraction (ZIP inside ZIP)

Automatically searches for .rnx files

Automatic Filtering
Processes only observation files (e.g., *_MO.rnx)
Ignores CN / EN / GN / RN files.

Automatic Folder Structure
INBOX_DROP – input files
OUTBOX_CONVERTED – converted output files
PROCESSED – processed originals
ERRORS – failed files
LOGS – execution logs

Console-Free Execution
The application is compiled as a Windows .exe without console window.

WORKFLOW

A ZIP or RINEX 3 file is copied into INBOX_DROP

The application:
-extracts archives (if ZIP)
-searches for .rnx files
-filters relevant observation files
-runs GFZRNX
-The converted file is saved in OUTBOX_CONVERTED
-The original file is moved to PROCESSED

!!!!!!!!! At the end, after drag & drop, click “Deschide OUTBOX_CONVERTED” to access the converted files.

REQUIREMENTS
Windows 10 / 11
gfzrnx_2.2.0_win11_64.exe in the same directory

Python is NOT required when using the compiled .exe version

----------------------------------------------------------------------------------------------------------------------------------------------------------------------
END OF DOCUMENT