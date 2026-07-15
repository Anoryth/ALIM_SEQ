<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="fr_FR">
<context>
    <name></name>
    <message>
        <location filename="../config_tab.py" line="31"/>
        <source>Logical name of the supply (JSON key: supplies.&lt;name&gt;).</source>
        <translation>Nom logique de l&apos;alimentation (clé JSON : supplies.&lt;nom&gt;).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="32"/>
        <source>Model</source>
        <translation>Modèle</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="32"/>
        <source>R&amp;S HMP model (JSON key: model).</source>
        <translation>Modèle R&amp;S HMP (clé JSON : model).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="33"/>
        <source>VISA address</source>
        <translation>Adresse VISA</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="34"/>
        <source>VISA resource, e.g. TCPIP0::192.168.0.10::5025::SOCKET (JSON key: resource).</source>
        <translation>Ressource VISA, ex. TCPIP0::192.168.0.10::5025::SOCKET (clé JSON : resource).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="40"/>
        <source>Channel name, used everywhere in the app (JSON key: channels.&lt;label&gt;).</source>
        <translation>Nom de la voie, utilisé partout dans l&apos;app (clé JSON : channels.&lt;label&gt;).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="41"/>
        <source>Supply</source>
        <translation>Alimentation</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="41"/>
        <source>Supply that carries the channel (JSON key: supply).</source>
        <translation>Alimentation qui porte la voie (clé JSON : supply).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="42"/>
        <source>Channel</source>
        <translation>Voie</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="42"/>
        <source>Physical channel 1..N of the supply (JSON key: channel).</source>
        <translation>Canal physique 1..N de l&apos;alimentation (clé JSON : channel).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="43"/>
        <source>Negative rail</source>
        <translation>Rail négatif</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="44"/>
        <source>Channel wired in reverse to produce a negative voltage (JSON key: negative).</source>
        <translation>Voie câblée en inverse pour produire une tension négative (clé JSON : negative).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="45"/>
        <source>Initial V (V)</source>
        <translation>V initiale (V)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="45"/>
        <source>Setpoint voltage at startup (JSON key: default_voltage).</source>
        <translation>Tension de consigne au démarrage (clé JSON : default_voltage).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="46"/>
        <source>Initial I (A)</source>
        <translation>I initiale (A)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="46"/>
        <source>Current limit at startup (JSON key: default_current).</source>
        <translation>Limite de courant au démarrage (clé JSON : default_current).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="47"/>
        <source>V max (V)</source>
        <translation>V max (V)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="47"/>
        <source>Maximum voltage allowed for the channel (JSON key: max_voltage).</source>
        <translation>Tension maximale autorisée pour la voie (clé JSON : max_voltage).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="48"/>
        <source>I max (A)</source>
        <translation>I max (A)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="48"/>
        <source>Maximum current allowed for the channel (JSON key: max_current).</source>
        <translation>Courant maximal autorisé pour la voie (clé JSON : max_current).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="54"/>
        <source>Name of the series group, driveable like a channel (JSON key: groups.&lt;name&gt;).</source>
        <translation>Nom du groupe série, pilotable comme une voie (clé JSON : groups.&lt;nom&gt;).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="55"/>
        <source>Member channels</source>
        <translation>Voies membres</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="55"/>
        <source>Channels in series, comma-separated (JSON key: members).</source>
        <translation>Voies en série, séparées par des virgules (clé JSON : members).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="56"/>
        <source>Split</source>
        <translation>Répartition</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="57"/>
        <source>Voltage split: balanced (equal) or fill (fill). JSON key: split.</source>
        <translation>Répartition de la tension : équilibrée (equal) ou remplissage (fill). Clé JSON : split.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="58"/>
        <source>V max (V) — 0 = auto</source>
        <translation>V max (V) — 0 = auto</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="59"/>
        <source>Group max voltage; 0 = sum of members (JSON key: max_voltage).</source>
        <translation>Tension max du groupe ; 0 = somme des membres (clé JSON : max_voltage).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="60"/>
        <source>I max (A) — 0 = auto</source>
        <translation>I max (A) — 0 = auto</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="61"/>
        <source>Group max current; 0 = smallest of the members (JSON key: max_current).</source>
        <translation>Courant max du groupe ; 0 = plus petit des membres (clé JSON : max_current).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="67"/>
        <source>Sensor name (JSON key: temperatures.&lt;name&gt;).</source>
        <translation>Nom du capteur (clé JSON : temperatures.&lt;nom&gt;).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="68"/>
        <source>NI channel</source>
        <translation>Voie NI</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="68"/>
        <source>NI analog input, e.g. ai0 (JSON key: channel).</source>
        <translation>Entrée analogique NI, ex. ai0 (clé JSON : channel).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="69"/>
        <source>Warning threshold (°C)</source>
        <translation>Seuil alerte (°C)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="69"/>
        <source>Warning temperature (JSON key: warning).</source>
        <translation>Température d&apos;alerte (clé JSON : warning).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="70"/>
        <source>Critical threshold (°C)</source>
        <translation>Seuil critique (°C)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="71"/>
        <source>Critical temperature triggering the power-down (JSON key: critical).</source>
        <translation>Température critique déclenchant la désalimentation (clé JSON : critical).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="72"/>
        <source>Required channels</source>
        <translation>Voies requises</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="73"/>
        <source>Sensor considered only if these channels are ON (JSON key: requires).</source>
        <translation>Capteur pris en compte seulement si ces voies sont ON (clé JSON : requires).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="74"/>
        <source>Plausible T min (°C)</source>
        <translation>T plausible min (°C)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="74"/>
        <source>Below: sensor in FAULT (JSON key: valid_min).</source>
        <translation>En dessous : capteur en DÉFAUT (clé JSON : valid_min).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="75"/>
        <source>Plausible T max (°C)</source>
        <translation>T plausible max (°C)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="75"/>
        <source>Above: sensor in FAULT (JSON key: valid_max).</source>
        <translation>Au-dessus : capteur en DÉFAUT (clé JSON : valid_max).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="76"/>
        <source>Converter</source>
        <translation>Convertisseur</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="77"/>
        <source>Voltage→°C conversion; double-click opens the assistant (JSON key: converter).</source>
        <translation>Conversion tension→°C ; double-cliquer ouvre l&apos;assistant (clé JSON : converter).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="78"/>
        <source>Reference channel</source>
        <translation>Voie de référence</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="78"/>
        <source>Channel providing the bridge voltage (JSON key: ref_channel).</source>
        <translation>Voie fournissant la tension du pont (clé JSON : ref_channel).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="79"/>
        <source>Expected ref V (V)</source>
        <translation>V réf. attendue (V)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="79"/>
        <source>Expected reference voltage (JSON key: ref_voltage).</source>
        <translation>Tension de référence attendue (clé JSON : ref_voltage).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="80"/>
        <source>Ref. tolerance</source>
        <translation>Tolérance réf.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="80"/>
        <source>Tolerated relative deviation on the reference (JSON key: ref_tol).</source>
        <translation>Écart relatif toléré sur la référence (clé JSON : ref_tol).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="81"/>
        <source>NI input min (V)</source>
        <translation>Entrée NI min (V)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="81"/>
        <source>Lower bound of the NI input range (JSON key: ai_min).</source>
        <translation>Borne basse de la plage d&apos;entrée NI (clé JSON : ai_min).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="82"/>
        <source>NI input max (V)</source>
        <translation>Entrée NI max (V)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="82"/>
        <source>Upper bound of the NI input range (JSON key: ai_max).</source>
        <translation>Borne haute de la plage d&apos;entrée NI (clé JSON : ai_max).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="88"/>
        <source>Relay instrument name (JSON key: instruments.&lt;name&gt;).</source>
        <translation>Nom de l&apos;instrument relais (clé JSON : instruments.&lt;nom&gt;).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="89"/>
        <source>Driver</source>
        <translation>Driver</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="89"/>
        <source>Relay driver (only MOCK-RELAY exists for now).</source>
        <translation>Pilote du relais (seul MOCK-RELAY existe pour l&apos;instant).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="90"/>
        <source>Outputs</source>
        <translation>Sorties</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="90"/>
        <source>Output labels, comma-separated (e.g. K1, K2).</source>
        <translation>Labels des sorties, séparés par des virgules (ex. K1, K2).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="91"/>
        <source>Closed at shutdown</source>
        <translation>Fermées à l&apos;arrêt</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="92"/>
        <source>Outputs left CLOSED in the safe state (the others are open), comma-separated. Empty = all open.</source>
        <translation>Sorties laissées FERMÉES à l&apos;état de sécurité (les autres sont ouvertes), séparées par des virgules. Vide = toutes ouvertes.</translation>
    </message>
    <message>
        <location filename="../editor.py" line="151"/>
        <source>voltage + current limit</source>
        <translation>tension + limite courant</translation>
    </message>
    <message>
        <location filename="../editor.py" line="152"/>
        <location filename="../editor.py" line="153"/>
        <source>channel = expr</source>
        <translation>voie = expr</translation>
    </message>
    <message>
        <location filename="../editor.py" line="152"/>
        <source>voltage via formula</source>
        <translation>tension via formule</translation>
    </message>
    <message>
        <location filename="../editor.py" line="153"/>
        <source>current limit via formula</source>
        <translation>limite courant via formule</translation>
    </message>
    <message>
        <location filename="../editor.py" line="154"/>
        <location filename="../editor.py" line="155"/>
        <source>channel</source>
        <translation>voie</translation>
    </message>
    <message>
        <location filename="../editor.py" line="154"/>
        <source>switch on</source>
        <translation>allumer</translation>
    </message>
    <message>
        <location filename="../editor.py" line="155"/>
        <source>switch off</source>
        <translation>éteindre</translation>
    </message>
    <message>
        <location filename="../editor.py" line="156"/>
        <source>seconds</source>
        <translation>secondes</translation>
    </message>
    <message>
        <location filename="../editor.py" line="156"/>
        <source>pause (interruptible)</source>
        <translation>pause (interruptible)</translation>
    </message>
    <message>
        <location filename="../editor.py" line="157"/>
        <source>channel Vend duration</source>
        <translation>voie Vfin durée</translation>
    </message>
    <message>
        <location filename="../editor.py" line="157"/>
        <source>ramp from current value</source>
        <translation>rampe depuis la valeur</translation>
    </message>
    <message>
        <location filename="../editor.py" line="158"/>
        <source>channel Vstart Vend duration [steps]</source>
        <translation>voie Vdeb Vfin durée [pas]</translation>
    </message>
    <message>
        <location filename="../editor.py" line="159"/>
        <source>explicit ramp ([steps]=number of steps, integer≥2)</source>
        <translation>rampe explicite ([pas]=nb de pas, entier≥2)</translation>
    </message>
    <message>
        <location filename="../editor.py" line="160"/>
        <location filename="../editor.py" line="161"/>
        <source>set measured Itarget</source>
        <translation>réglée mesurée Icible</translation>
    </message>
    <message>
        <location filename="../editor.py" line="160"/>
        <source>fixed-step servo (SERVO=alias)</source>
        <translation>asserv. pas fixe (SERVO=alias)</translation>
    </message>
    <message>
        <location filename="../editor.py" line="161"/>
        <source>adaptive-step servo</source>
        <translation>asserv. pas adaptatif</translation>
    </message>
    <message>
        <location filename="../editor.py" line="162"/>
        <source>channel op val</source>
        <translation>voie op val</translation>
    </message>
    <message>
        <location filename="../editor.py" line="162"/>
        <source>wait for current cond.</source>
        <translation>attend cond. courant</translation>
    </message>
    <message>
        <location filename="../editor.py" line="163"/>
        <source>sensor op val</source>
        <translation>capteur op val</translation>
    </message>
    <message>
        <location filename="../editor.py" line="163"/>
        <source>wait for temperature cond.</source>
        <translation>attend cond. température</translation>
    </message>
    <message>
        <location filename="../editor.py" line="164"/>
        <source>text</source>
        <translation>texte</translation>
    </message>
    <message>
        <location filename="../editor.py" line="164"/>
        <source>message to the log</source>
        <translation>message au journal</translation>
    </message>
    <message>
        <location filename="../editor.py" line="165"/>
        <source>switches off all channels</source>
        <translation>éteint toutes les voies</translation>
    </message>
    <message>
        <location filename="../editor.py" line="166"/>
        <source>output ON|OFF</source>
        <translation>sortie ON|OFF</translation>
    </message>
    <message>
        <location filename="../editor.py" line="166"/>
        <source>closes/opens a relay output</source>
        <translation>ferme/ouvre une sortie de relais</translation>
    </message>
    <message>
        <location filename="../editor.py" line="173"/>
        <source>SETV &lt;channel&gt; = &lt;expr&gt;</source>
        <translation>SETV &lt;voie&gt; = &lt;expr&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="174"/>
        <source>SETI &lt;channel&gt; = &lt;expr&gt;</source>
        <translation>SETI &lt;voie&gt; = &lt;expr&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="175"/>
        <source>ON &lt;channel&gt;</source>
        <translation>ON &lt;voie&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="176"/>
        <source>OFF &lt;channel&gt;</source>
        <translation>OFF &lt;voie&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="177"/>
        <source>WAIT &lt;s&gt;</source>
        <translation>WAIT &lt;s&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="178"/>
        <source>RAMP &lt;channel&gt; &lt;Vend&gt; &lt;duration&gt;</source>
        <translation>RAMP &lt;voie&gt; &lt;Vfin&gt; &lt;duree&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="179"/>
        <source>SERVO_LIN &lt;set&gt; &lt;measured&gt; &lt;Itarget&gt; step=0.02 tol=0.01</source>
        <translation>SERVO_LIN &lt;reglee&gt; &lt;mesuree&gt; &lt;Icible&gt; step=0.02 tol=0.01</translation>
    </message>
    <message>
        <location filename="../editor.py" line="180"/>
        <source>SERVO_ADAPT &lt;set&gt; &lt;measured&gt; &lt;Itarget&gt; step=0.5 tol=0.01</source>
        <translation>SERVO_ADAPT &lt;reglee&gt; &lt;mesuree&gt; &lt;Icible&gt; step=0.5 tol=0.01</translation>
    </message>
    <message>
        <location filename="../editor.py" line="181"/>
        <source>WAIT_CURRENT &lt;channel&gt; &gt;= &lt;val&gt; timeout=10</source>
        <translation>WAIT_CURRENT &lt;voie&gt; &gt;= &lt;val&gt; timeout=10</translation>
    </message>
    <message>
        <location filename="../editor.py" line="182"/>
        <source>WAIT_TEMP &lt;sensor&gt; &lt;= &lt;val&gt; timeout=10</source>
        <translation>WAIT_TEMP &lt;capteur&gt; &lt;= &lt;val&gt; timeout=10</translation>
    </message>
    <message>
        <location filename="../editor.py" line="183"/>
        <source>LOG &lt;text&gt;</source>
        <translation>LOG &lt;texte&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="185"/>
        <source>RELAY &lt;output&gt; ON</source>
        <translation>RELAY &lt;sortie&gt; ON</translation>
    </message>
</context>
<context>
    <name>AlimSeqQtGUI</name>
    <message>
        <location filename="../main_window.py" line="33"/>
        <location filename="../main_window.py" line="946"/>
        <source>No sequence loaded.</source>
        <translation>Aucune séquence chargée.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="76"/>
        <location filename="../main_window.py" line="548"/>
        <source>ALIM_SEQ — Power-supply sequencer  v{}</source>
        <translation>ALIM_SEQ — Séquenceur d&apos;alimentation  v{}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="116"/>
        <source>Last profile not found, ignored: {}</source>
        <translation>Dernier profil introuvable, ignoré : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="121"/>
        <source>Last profile invalid, ignored ({}).</source>
        <translation>Dernier profil invalide, ignoré ({}).</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="155"/>
        <location filename="../main_window.py" line="1409"/>
        <source>Safety: OK</source>
        <translation>Sécurité : OK</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="174"/>
        <source>Total power delivered (sum of channels)</source>
        <translation>Puissance totale délivrée (somme des voies)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="177"/>
        <source>Current configuration file</source>
        <translation>Fichier de configuration courant</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="185"/>
        <source>Log</source>
        <translation>Journal</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="190"/>
        <source>Search the log…</source>
        <translation>Rechercher dans le journal…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="192"/>
        <source>Search</source>
        <translation>Rechercher</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="231"/>
        <source>⛔ EMERGENCY STOP</source>
        <translation>⛔ ARRÊT D&apos;URGENCE</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="235"/>
        <source>ABRUPT, immediate cut-off of all channels (shortcut Ctrl+Shift+X).
No confirmation by default — see “View → Confirm emergency stop”.</source>
        <translation>Coupure BRUTALE et immédiate de toutes les voies (raccourci Ctrl+Maj+X).
Sans confirmation par défaut — voir « Affichage → Confirmer l&apos;arrêt d&apos;urgence ».</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="240"/>
        <source>⏹ Shutdown sequence</source>
        <translation>⏹ Séquentiel d&apos;arrêt</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="243"/>
        <source>ORDERLY (soft) power-down: runs the shutdown sequence, or switches channels off in reverse order if none is defined</source>
        <translation>Désalimentation ORDONNÉE (douce) : exécute la séquence d&apos;arrêt, ou éteint les voies dans l&apos;ordre inverse si aucune n&apos;est définie</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="248"/>
        <location filename="../main_window.py" line="1079"/>
        <source>Rearm</source>
        <translation>Réarmer</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="250"/>
        <source>Release the safety lock after a trip</source>
        <translation>Lève le verrou de sécurité après un déclenchement</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="254"/>
        <source>All OFF</source>
        <translation>Tout OFF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="256"/>
        <source>Switch off all channels (no ramp, without tripping safety)</source>
        <translation>Éteint toutes les voies (sans rampe, mais sans déclencher la sécurité)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="304"/>
        <source>No hardware driven — simulated model.</source>
        <translation>Aucun matériel piloté — modèle simulé.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="309"/>
        <source>Driving REAL hardware — check the config limits.</source>
        <translation>Pilotage de matériel RÉEL — vérifier les limites de la config.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="381"/>
        <source>Hardware connection</source>
        <translation>Connexion matériel</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="382"/>
        <source>Cannot connect to the hardware:

{}

The GUI stays in disconnected mode. Fix the problem then “Reconnect”.</source>
        <translation>Impossible de se connecter au matériel :

{}

L&apos;IHM reste en mode déconnecté. Corriger le problème puis « Reconnecter ».</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="389"/>
        <source>&amp;File</source>
        <translation>&amp;Fichier</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="390"/>
        <source>Open a sequence…</source>
        <translation>Ouvrir une séquence…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="392"/>
        <source>Configuration wizard…</source>
        <translation>Assistant de configuration…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="393"/>
        <source>Load a configuration…</source>
        <translation>Charger une configuration…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="394"/>
        <location filename="../main_window.py" line="592"/>
        <source>Save configuration as…</source>
        <translation>Enregistrer la configuration sous…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="396"/>
        <source>Reopen a test (replay)…</source>
        <translation>Rouvrir un essai (relecture)…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="397"/>
        <source>Compare two tests…</source>
        <translation>Comparer deux essais…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="398"/>
        <source>Generate a test report…</source>
        <translation>Générer un rapport d&apos;essai…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="399"/>
        <source>Reopen the last profile at startup</source>
        <translation>Rouvrir le dernier profil au démarrage</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="405"/>
        <location filename="../main_window.py" line="1507"/>
        <source>Quit</source>
        <translation>Quitter</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="407"/>
        <source>&amp;View</source>
        <translation>&amp;Affichage</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="408"/>
        <source>Dark theme</source>
        <translation>Thème sombre</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="412"/>
        <source>Compact mode (hide the log)</source>
        <translation>Mode compact (masquer le journal)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="415"/>
        <source>Sound alert on critical safety</source>
        <translation>Alerte sonore en sécurité critique</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="419"/>
        <source>Confirm emergency stop</source>
        <translation>Confirmer l&apos;arrêt d&apos;urgence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="423"/>
        <source>If checked, emergency stop asks for confirmation (otherwise immediate cut-off).</source>
        <translation>Si coché, l&apos;arrêt d&apos;urgence demande une confirmation (sinon coupure immédiate).</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="425"/>
        <source>Generate the report at end of test</source>
        <translation>Générer le rapport en fin d&apos;essai</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="430"/>
        <source>At end of recording, prompt for the conclusion then generate the PDF report. The report is ALWAYS generated automatically on a safety trip.</source>
        <translation>En fin d&apos;enregistrement, proposer la conclusion puis générer le rapport PDF. Le rapport est TOUJOURS généré automatiquement sur déclenchement de sécurité.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="437"/>
        <location filename="../main_window.py" line="474"/>
        <source>Language</source>
        <translation>Langue</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="448"/>
        <source>&amp;Help</source>
        <translation>&amp;Aide</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="449"/>
        <location filename="../main_window.py" line="672"/>
        <source>User manual</source>
        <translation>Manuel utilisateur</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="451"/>
        <location filename="../main_window.py" line="648"/>
        <source>Keyboard shortcuts</source>
        <translation>Raccourcis clavier</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="452"/>
        <location filename="../main_window.py" line="708"/>
        <source>Sequence command reference</source>
        <translation>Référence des commandes de séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="453"/>
        <source>Where are my files?</source>
        <translation>Où sont mes fichiers ?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="455"/>
        <source>About</source>
        <translation>À propos</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="475"/>
        <source>The language change will take effect after restarting ALIM_SEQ.

Quit now?</source>
        <translation>Le changement de langue prendra effet après le redémarrage d&apos;ALIM_SEQ.

Quitter maintenant ?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="568"/>
        <source>Profile</source>
        <translation>Profil</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="568"/>
        <location filename="../main_window.py" line="1079"/>
        <location filename="../main_window.py" line="1085"/>
        <source>Stop the sequence first.</source>
        <translation>Arrêter la séquence d&apos;abord.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="582"/>
        <source>Switch to this profile and reload the hardware?

{}</source>
        <translation>Basculer sur ce profil et recharger le matériel ?

{}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="606"/>
        <source>✓ Saved to {}.</source>
        <translation>✓ Enregistré dans {}.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="608"/>
        <source>Configuration saved as: {}</source>
        <translation>Configuration enregistrée sous : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="611"/>
        <source>SIMULATION</source>
        <translation>SIMULATION</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="306"/>
        <location filename="../main_window.py" line="611"/>
        <source>REAL HARDWARE</source>
        <translation>MATÉRIEL RÉEL</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="614"/>
        <source>About ALIM_SEQ</source>
        <translation>À propos d&apos;ALIM_SEQ</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="616"/>
        <source>&lt;b&gt;ALIM_SEQ&lt;/b&gt; — Power-supply sequencer v{version}&lt;br&gt;&lt;br&gt;R&amp;S HMP (4040/4030/2030/2020) control + NI acquisition.&lt;br&gt;Sequences, servo control, thermal monitoring and safety.&lt;br&gt;Qt interface (PySide6).&lt;br&gt;&lt;br&gt;&lt;b&gt;Mode:&lt;/b&gt; {mode}&lt;br&gt;&lt;b&gt;Configuration:&lt;/b&gt; {cfg}&lt;br&gt;&lt;b&gt;Log:&lt;/b&gt; {log}&lt;br&gt;&lt;br&gt;&lt;b&gt;Test folders:&lt;/b&gt; each recording creates &lt;code&gt;logs/essais/YYYYMMDD_HHMMSS[_&amp;lt;name&amp;gt;]/&lt;/code&gt; (measurements, config, sequence, log, metadata) from which the &lt;b&gt;PDF test report&lt;/b&gt; can be regenerated at any time (&lt;i&gt;File → Generate a test report…&lt;/i&gt;). The report issues no compliance verdict: the conclusion is the operator&apos;s.&lt;br&gt;&lt;br&gt;&lt;i&gt;Laboratory use — check the configuration limits before any test on real hardware.&lt;/i&gt;</source>
        <translation>&lt;b&gt;ALIM_SEQ&lt;/b&gt; — Séquenceur d&apos;alimentation v{version}&lt;br&gt;&lt;br&gt;Pilotage R&amp;S HMP (4040/4030/2030/2020) + acquisition NI.&lt;br&gt;Séquences, asservissement, surveillance thermique et sécurité.&lt;br&gt;Interface Qt (PySide6).&lt;br&gt;&lt;br&gt;&lt;b&gt;Mode :&lt;/b&gt; {mode}&lt;br&gt;&lt;b&gt;Configuration :&lt;/b&gt; {cfg}&lt;br&gt;&lt;b&gt;Journal :&lt;/b&gt; {log}&lt;br&gt;&lt;br&gt;&lt;b&gt;Dossiers d&apos;essai :&lt;/b&gt; chaque enregistrement crée &lt;code&gt;logs/essais/AAAAMMJJ_HHMMSS[_&amp;lt;nom&amp;gt;]/&lt;/code&gt; (mesures, config, séquence, journal, métadonnées) d&apos;où le &lt;b&gt;rapport d&apos;essai PDF&lt;/b&gt; se régénère à tout moment (&lt;i&gt;Fichier → Générer un rapport d&apos;essai…&lt;/i&gt;). Le rapport n&apos;émet aucun verdict de conformité : la conclusion est celle de l&apos;opérateur.&lt;br&gt;&lt;br&gt;&lt;i&gt;Usage laboratoire — vérifier les limites de la configuration avant tout essai sur matériel réel.&lt;/i&gt;</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="698"/>
        <location filename="../main_window.py" line="1184"/>
        <source>Open the PDF</source>
        <translation>Ouvrir le PDF</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="730"/>
        <source>🎛  Control</source>
        <translation>🎛  Contrôle</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="731"/>
        <source>⚙  Configuration</source>
        <translation>⚙  Configuration</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="732"/>
        <source>📝  Sequence editor</source>
        <translation>📝  Éditeur de séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="736"/>
        <source>📈  Chart</source>
        <translation>📈  Graphe</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="739"/>
        <source>🧪  Simulation</source>
        <translation>🧪  Simulation</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="753"/>
        <source>Temperatures (°C)</source>
        <translation>Températures (°C)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="756"/>
        <source>Plotted quantity. Hover the chart to read values; click a curve name in the legend to hide/show it.</source>
        <translation>Grandeur tracée. Survoler le graphe pour lire les valeurs ; cliquer un nom de courbe dans la légende la masque/affiche.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="777"/>
        <source>Window:</source>
        <translation>Fenêtre :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="801"/>
        <source>Chart exported: {}</source>
        <translation>Graphe exporté : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="808"/>
        <source>Export chart data</source>
        <translation>Exporter les données du graphe</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="815"/>
        <source>Chart data exported: {}</source>
        <translation>Données du graphe exportées : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="855"/>
        <source>Series channels (voltage = sum)</source>
        <translation>Voies en série (tension = somme)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="865"/>
        <source>Temperatures</source>
        <translation>Températures</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="892"/>
        <location filename="../main_window.py" line="1042"/>
        <source>Sequence</source>
        <translation>Séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="894"/>
        <source>File:</source>
        <translation>Fichier :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="899"/>
        <location filename="../main_window.py" line="909"/>
        <source>Browse…</source>
        <translation>Parcourir…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="901"/>
        <source>Load/Check</source>
        <translation>Charger/Vérifier</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="904"/>
        <source>Shutdown seq.:</source>
        <translation>Séq. d&apos;arrêt :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="911"/>
        <source>Check</source>
        <translation>Vérifier</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="913"/>
        <source>(empty = automatic channel power-off in reverse order)</source>
        <translation>(vide = extinction automatique des voies dans l&apos;ordre inverse)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="917"/>
        <source>▶ Start the sequence</source>
        <translation>▶ Démarrer la séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="919"/>
        <source>Loads the file above and runs it (Ctrl+Enter from the editor)</source>
        <translation>Charge le fichier ci-dessus et l&apos;exécute (Ctrl+Entrée depuis l&apos;éditeur)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="766"/>
        <location filename="../main_window.py" line="791"/>
        <location filename="../main_window.py" line="922"/>
        <location filename="../main_window.py" line="1479"/>
        <source>⏸ Pause</source>
        <translation>⏸ Pause</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="128"/>
        <source>Running — L{}: {}</source>
        <translation>En cours — L{} : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="544"/>
        <source>Interactive configuration editing. Renamed or deleted channels/groups/sensors are checked on “Apply”.</source>
        <translation>Édition interactive de la configuration. Les voies/groupes/capteurs renommés ou supprimés sont vérifiés à « Appliquer ».</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="571"/>
        <source>Load a configuration (profile)</source>
        <translation>Charger une configuration (profil)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="572"/>
        <source>Configuration (*.json);;All (*)</source>
        <translation>Configuration (*.json);;Tous (*)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="578"/>
        <source>Invalid configuration</source>
        <translation>Configuration invalide</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="581"/>
        <source>Load the profile</source>
        <translation>Charger le profil</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="593"/>
        <source>Configuration (*.json)</source>
        <translation>Configuration (*.json)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="749"/>
        <source>Quantity:</source>
        <translation>Grandeur :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="754"/>
        <source>Currents (A)</source>
        <translation>Courants (A)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="755"/>
        <source>Voltages (V)</source>
        <translation>Tensions (V)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="764"/>
        <source>(── measured · – – warning · ··· critical)</source>
        <translation>(── mesure · – – warning · ··· critical)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="770"/>
        <source>🗑 Clear</source>
        <translation>🗑 Effacer</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="795"/>
        <source>Export the chart</source>
        <translation>Exporter le graphe</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="795"/>
        <source>PNG image (*.png)</source>
        <translation>Image PNG (*.png)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="803"/>
        <source>Export</source>
        <translation>Export</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="804"/>
        <source>Failed to save the PNG.</source>
        <translation>Échec de l&apos;enregistrement du PNG.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="846"/>
        <source>Power channels</source>
        <translation>Voies d&apos;alimentation</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="877"/>
        <source>Relays</source>
        <translation>Relais</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="924"/>
        <source>Suspend/resume the sequence (also freezes WAITs)</source>
        <translation>Suspend/reprend la séquence (gèle aussi les WAIT)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="929"/>
        <source>Step-by-step</source>
        <translation>Pas-à-pas</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="930"/>
        <source>Runs the sequence action by action (each action waits for “Next step”).</source>
        <translation>Exécute la séquence action par action (chaque action attend « Étape suivante »).</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="934"/>
        <source>▶| Next step</source>
        <translation>▶| Étape suivante</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="936"/>
        <source>Allows the next action in step-by-step mode</source>
        <translation>Autorise l&apos;action suivante en mode pas-à-pas</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="951"/>
        <source>Measurement recording</source>
        <translation>Enregistrement des mesures</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="953"/>
        <location filename="../main_window.py" line="1482"/>
        <source>● Start recording</source>
        <translation>● Démarrer l&apos;enregistrement</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="956"/>
        <source>Record during the sequence</source>
        <translation>Enregistrer pendant la séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="962"/>
        <source>📌 Marker</source>
        <translation>📌 Marqueur</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="963"/>
        <source>Place a timestamped marker (note) — Ctrl+M. Appears on the chart and in the test report.</source>
        <translation>Poser un repère horodaté (note) — Ctrl+M. Apparaît sur le graphe et dans le rapport d&apos;essai.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="974"/>
        <location filename="../main_window.py" line="1091"/>
        <location filename="../main_window.py" line="1100"/>
        <source>Reconnect</source>
        <translation>Reconnecter</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="975"/>
        <source>Reconnect the hardware (VISA / NI-DAQmx) after a communication loss</source>
        <translation>Reconnecte le matériel (VISA / NI-DAQmx) après une perte de communication</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="986"/>
        <source>Choose a sequence</source>
        <translation>Choisir une séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="986"/>
        <location filename="../main_window.py" line="1012"/>
        <source>Sequence (*.seq *.txt);;All (*)</source>
        <translation>Séquence (*.seq *.txt);;Tous (*)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="994"/>
        <location filename="../main_window.py" line="1027"/>
        <source>File not found</source>
        <translation>Fichier introuvable</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1002"/>
        <source>Invalid sequence</source>
        <translation>Séquence invalide</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1003"/>
        <source>Invalid sequence.</source>
        <translation>Séquence invalide.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1006"/>
        <source>{} action(s) from {}.</source>
        <translation>{} action(s) depuis {}.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1011"/>
        <source>Choose a shutdown sequence</source>
        <translation>Choisir une séquence d&apos;arrêt</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1022"/>
        <location filename="../main_window.py" line="1037"/>
        <source>Shutdown sequence</source>
        <translation>Séquentiel d&apos;arrêt</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1023"/>
        <source>Empty: automatic channel power-off in reverse order.</source>
        <translation>Vide : extinction automatique des voies dans l&apos;ordre inverse.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1034"/>
        <source>Invalid shutdown sequence</source>
        <translation>Séquentiel d&apos;arrêt invalide</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1038"/>
        <source>Valid file: {}</source>
        <translation>Fichier valide : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1042"/>
        <source>Already running.</source>
        <translation>Déjà en cours.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1049"/>
        <location filename="../main_window.py" line="1441"/>
        <source>Hardware not connected</source>
        <translation>Matériel non connecté</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1050"/>
        <source>The hardware is not connected: cannot start a sequence.

Check the link (VISA / NI-DAQmx) then “Reconnect”.</source>
        <translation>Le matériel n&apos;est pas connecté : impossible de lancer une séquence.

Vérifier la liaison (VISA / NI-DAQmx) puis « Reconnecter ».</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1054"/>
        <source>Safety</source>
        <translation>Sécurité</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1054"/>
        <source>Rearm the safety before starting.</source>
        <translation>Réarmer la sécurité avant de démarrer.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="637"/>
        <location filename="../main_window.py" line="1071"/>
        <source>Emergency stop</source>
        <translation>Arrêt d&apos;urgence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="638"/>
        <source>Save the sequence</source>
        <translation>Enregistrer la séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="639"/>
        <source>Open a sequence</source>
        <translation>Ouvrir une séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="640"/>
        <source>Check the sequence</source>
        <translation>Vérifier la séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="641"/>
        <source>Load and run the sequence</source>
        <translation>Charger et lancer la séquence</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="642"/>
        <source>Start/stop recording</source>
        <translation>Démarrer/arrêter l'enregistrement</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="643"/>
        <source>Place an operator marker</source>
        <translation>Ajouter un marqueur</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="692"/>
        <source>Manual not found in this installation.</source>
        <translation>Manuel introuvable dans cette installation.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1072"/>
        <source>ABRUPT, immediate cut-off of all channels.
Confirm?</source>
        <translation>Coupure BRUTALE et immédiate de toutes les voies.
Confirmer ?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1075"/>
        <source>EMERGENCY STOP (operator)</source>
        <translation>ARRÊT D&apos;URGENCE (opérateur)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1085"/>
        <location filename="../main_window.py" line="1094"/>
        <location filename="../main_window.py" line="1096"/>
        <source>Reconnection</source>
        <translation>Reconnexion</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1087"/>
        <source>Reconnecting…</source>
        <translation>Reconnexion…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1094"/>
        <source>Hardware reconnected.</source>
        <translation>Matériel reconnecté.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1097"/>
        <source>Failure:

{}</source>
        <translation>Échec :

{}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1106"/>
        <source>All channels cut off (All OFF).</source>
        <translation>Toutes les voies coupées (Tout OFF).</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1114"/>
        <source>New test</source>
        <translation>Nouvel essai</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1117"/>
        <location filename="../main_window.py" line="1119"/>
        <source>(optional)</source>
        <translation>(facultatif)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1120"/>
        <source>Test name:</source>
        <translation>Nom de l&apos;essai :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1121"/>
        <source>Operator:</source>
        <translation>Opérateur :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1122"/>
        <source>This information will appear in the test report.</source>
        <translation>Ces informations figureront dans le rapport d&apos;essai.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1142"/>
        <source>Test conclusion</source>
        <translation>Conclusion de l&apos;essai</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1145"/>
        <source>Operator conclusion (optional) — the report issues no compliance verdict:</source>
        <translation>Conclusion de l&apos;opérateur (facultative) — le rapport n&apos;émet aucun verdict de conformité :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1166"/>
        <source>Generating the test report…</source>
        <translation>Génération du rapport d&apos;essai en cours…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1171"/>
        <source>Report generation failed: {}</source>
        <translation>Échec de génération du rapport : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1178"/>
        <source>Test report generated: {}</source>
        <translation>Rapport d&apos;essai généré : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1182"/>
        <source>Test report</source>
        <translation>Rapport d&apos;essai</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1183"/>
        <source>Report generated:
{}</source>
        <translation>Rapport généré :
{}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1199"/>
        <source>No test folder in logs/essais.</source>
        <translation>Aucun dossier d&apos;essai dans logs/essais.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1213"/>
        <source>Test folder:</source>
        <translation>Dossier d&apos;essai :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1219"/>
        <source>Generate a test report</source>
        <translation>Générer un rapport d&apos;essai</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1228"/>
        <source>Reopen a test (replay)</source>
        <translation>Rouvrir un essai (relecture)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1250"/>
        <source>Welcome to ALIM_SEQ</source>
        <translation>Bienvenue dans ALIM_SEQ</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1251"/>
        <source>Configure your bench now?

The wizard detects the power supplies (VISA scan) and prepares a starting configuration. You can relaunch it via File → Configuration wizard.</source>
        <translation>Configurer votre banc maintenant ?

L&apos;assistant détecte les alimentations (scan VISA) et prépare une configuration de départ. Vous pourrez le relancer via Fichier → Assistant de configuration.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1274"/>
        <source>Configuration wizard</source>
        <translation>Assistant de configuration</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1275"/>
        <source>Configuration generated and loaded into the Configuration tab.
Check the channels (names, limits), then click “✓ Apply (reload hardware)”.</source>
        <translation>Configuration générée et chargée dans l&apos;onglet Configuration.
Vérifiez les voies (noms, limites), puis cliquez « ✓ Appliquer (recharge matériel) ».</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1281"/>
        <source>Compare — 1st test (A)</source>
        <translation>Comparer — 1ᵉʳ essai (A)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1284"/>
        <source>Compare — 2nd test (B)</source>
        <translation>Comparer — 2ᵉ essai (B)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1295"/>
        <source>Completed</source>
        <translation>Terminé</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1295"/>
        <source>Interrupted</source>
        <translation>Interrompu</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1296"/>
        <source>SAFETY TRIP</source>
        <translation>DÉCLENCHEMENT DE SÉCURITÉ</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1297"/>
        <source>in progress</source>
        <translation>en cours</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1310"/>
        <source>Marker</source>
        <translation>Marqueur</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1310"/>
        <source>Note (e.g. “I touched the capacitor”):</source>
        <translation>Note (ex. « J&apos;ai touché le condensateur ») :</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1314"/>
        <source>marker</source>
        <translation>marqueur</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1358"/>
        <source>~{:.0f}s remaining</source>
        <translation>~{:.0f}s restantes</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1362"/>
        <source>{} action(s)</source>
        <translation>{} action(s)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1365"/>
        <source>~{:.0f}s (excl. SERVO/WAIT_*)</source>
        <translation>~{:.0f}s (hors SERVO/WAIT_*)</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1397"/>
        <source>⏳ Connecting to the hardware…</source>
        <translation>⏳ Connexion au matériel en cours…</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1399"/>
        <source>⛔ NOT CONNECTED — check VISA / NI-DAQmx then “Reconnect”</source>
        <translation>⛔ NON CONNECTÉ — vérifier VISA / NI-DAQmx puis « Reconnecter »</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1401"/>
        <source>⛔ COMMUNICATION LOST: {}</source>
        <translation>⛔ PERTE DE COMMUNICATION : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1403"/>
        <source>⛔ SAFETY TRIPPED: {}</source>
        <translation>⛔ SÉCURITÉ DÉCLENCHÉE : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1405"/>
        <source>⚠ {} — reset the supply then “Reconnect”</source>
        <translation>⚠ {} — réarme l&apos;alim puis « Reconnecter »</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1407"/>
        <source>Safety: {} — {}</source>
        <translation>Sécurité : {} — {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1421"/>
        <source>Safety trip: automatic test-report generation.</source>
        <translation>Déclenchement de sécurité : génération automatique du rapport d&apos;essai.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1444"/>
        <source>Hardware connected</source>
        <translation>Matériel connecté</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1445"/>
        <source>meas {:.2f}s · temp {:.2f}s</source>
        <translation>mesures {:.2f}s · température {:.2f}s</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1451"/>
        <source>Current test folder: {}</source>
        <translation>Dossier d&apos;essai en cours : {}</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="791"/>
        <location filename="../main_window.py" line="1479"/>
        <source>▶ Resume</source>
        <translation>▶ Reprendre</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1471"/>
        <source>seq. start</source>
        <translation>début séq.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1471"/>
        <source>seq. end</source>
        <translation>fin séq.</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1481"/>
        <source>■ Stop recording</source>
        <translation>■ Arrêter l&apos;enregistrement</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1492"/>
        <source>Unsaved sequence</source>
        <translation>Séquence non enregistrée</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1493"/>
        <source>The sequence being edited has unsaved changes.
Save before quitting?</source>
        <translation>La séquence en cours d&apos;édition a des modifications non enregistrées.
Enregistrer avant de quitter ?</translation>
    </message>
    <message>
        <location filename="../main_window.py" line="1507"/>
        <source>Switch off the supplies and quit?</source>
        <translation>Couper les alimentations et quitter ?</translation>
    </message>
</context>
<context>
    <name>ChannelRowQt</name>
    <message>
        <location filename="../widgets.py" line="44"/>
        <source>Channel</source>
        <translation>Voie</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="45"/>
        <source>V setpoint</source>
        <translation>V consigne</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="46"/>
        <source>I limit</source>
        <translation>I limite</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="47"/>
        <source>Output</source>
        <translation>Sortie</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="48"/>
        <source>V measured</source>
        <translation>V mesurée</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="49"/>
        <source>I measured</source>
        <translation>I mesurée</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="50"/>
        <source>Mode</source>
        <translation>Mode</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="83"/>
        <source>Apply</source>
        <translation>Appliquer</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="88"/>
        <location filename="../widgets.py" line="186"/>
        <source>OFF</source>
        <translation>OFF</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="155"/>
        <location filename="../widgets.py" line="180"/>
        <source>⚠ Arm?</source>
        <translation>⚠ Armer ?</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="183"/>
        <source>ON</source>
        <translation>ON</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="189"/>
        <source>⏱ frozen</source>
        <translation>⏱ figé</translation>
    </message>
</context>
<context>
    <name>ConfigMixin</name>
    <message>
        <location filename="../config_tab.py" line="31"/>
        <location filename="../config_tab.py" line="54"/>
        <location filename="../config_tab.py" line="67"/>
        <source>Name</source>
        <translation>Nom</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="40"/>
        <source>Label</source>
        <translation>Libellé</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="88"/>
        <source>Instrument</source>
        <translation>Instrument</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="118"/>
        <source>Interactive configuration editing. Renamed or deleted channels/groups/sensors are checked on “Apply”.</source>
        <translation>Édition interactive de la configuration. Les voies/groupes/capteurs renommés ou supprimés sont vérifiés à « Appliquer ».</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="127"/>
        <source>VISA address of each supply. “Scan VISA” detects the connected instruments.</source>
        <translation>Adresse VISA de chaque alimentation. « Scanner VISA » détecte les instruments branchés.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="132"/>
        <location filename="../config_tab.py" line="152"/>
        <location filename="../config_tab.py" line="167"/>
        <location filename="../config_tab.py" line="183"/>
        <location filename="../config_tab.py" line="201"/>
        <source>+ Add</source>
        <translation>+ Ajouter</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="133"/>
        <location filename="../config_tab.py" line="153"/>
        <location filename="../config_tab.py" line="168"/>
        <location filename="../config_tab.py" line="184"/>
        <location filename="../config_tab.py" line="202"/>
        <source>− Remove</source>
        <translation>− Supprimer</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="135"/>
        <source>Scan VISA…</source>
        <translation>Scanner VISA…</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="138"/>
        <source>Test the connection…</source>
        <translation>Tester la connexion…</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="143"/>
        <source>Supplies</source>
        <translation>Alimentations</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="147"/>
        <source>A channel = one physical channel of a supply. “negative” for a rail wired in reverse.</source>
        <translation>Une voie = un canal physique d&apos;une alim. « négative » pour un rail câblé en inverse.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="157"/>
        <source>Channels</source>
        <translation>Voies</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="162"/>
        <source>Group = channels in SERIES (summed voltage, common current), driven by its name. Members = comma-separated channels. max=0 → auto.</source>
        <translation>Groupe = voies en SÉRIE (tension additionnée, courant commun), piloté par son nom. Membres = voies séparées par des virgules. max=0 → auto.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="172"/>
        <source>Groups</source>
        <translation>Groupes</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="177"/>
        <source>A sensor = one NI channel (ai…). “Converter…” opens the assistant (type + settings) and applies it directly, no copy-paste.</source>
        <translation>Un capteur = une voie NI (ai…). « Convertisseur… » ouvre l&apos;assistant (type + réglages) et l&apos;applique directement, sans copier-coller.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="185"/>
        <source>Converter…</source>
        <translation>Convertisseur…</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="189"/>
        <source>Temperatures</source>
        <translation>Températures</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="194"/>
        <source>Relays / actuators: an instrument exposes driveable &lt;b&gt;outputs&lt;/b&gt; (sequence: &lt;code&gt;RELAY &amp;lt;output&amp;gt; ON|OFF&lt;/code&gt;). Each output is brought back to its safe state at shutdown (open by default). No real hardware model is integrated yet (MOCK-RELAY = simulated relay).</source>
        <translation>Relais / actionneurs : un instrument expose des &lt;b&gt;sorties&lt;/b&gt; pilotables (séquence : &lt;code&gt;RELAY &amp;lt;sortie&amp;gt; ON|OFF&lt;/code&gt;). Chaque sortie est ramenée à son état de sécurité à l&apos;arrêt (ouverte par défaut). Aucun modèle matériel réel n&apos;est encore intégré (MOCK-RELAY = relais simulé).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="206"/>
        <source>Relays</source>
        <translation>Relais</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="211"/>
        <source>&lt;b&gt;Full configuration (JSON)&lt;/b&gt; — free editing. Synced with the forms: the active tab is authoritative on save.</source>
        <translation>&lt;b&gt;Configuration complète (JSON)&lt;/b&gt; — édition libre. Synchronisée avec les formulaires : l&apos;onglet actif fait foi à l&apos;enregistrement.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="216"/>
        <source>Advanced (JSON)</source>
        <translation>Avancé (JSON)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="226"/>
        <source>Converter assistant…</source>
        <translation>Assistant convertisseur…</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="227"/>
        <source>Reload the file</source>
        <translation>Recharger le fichier</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="228"/>
        <source>Check</source>
        <translation>Vérifier</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="229"/>
        <source>Save</source>
        <translation>Enregistrer</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="231"/>
        <source>✓ Apply (reload hardware)</source>
        <translation>✓ Appliquer (recharge matériel)</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="280"/>
        <source>Delete {} “{}”?</source>
        <translation>Supprimer {} « {} » ?</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="284"/>
        <source>Confirm deletion</source>
        <translation>Confirmer la suppression</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="290"/>
        <source>the supply</source>
        <translation>l&apos;alimentation</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="291"/>
        <source>Channels referencing it will need to be reassigned.</source>
        <translation>Les voies qui la référencent devront être réaffectées.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="318"/>
        <source>the channel</source>
        <translation>la voie</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="319"/>
        <source>References in groups/sensors/sequences will need to be fixed manually.</source>
        <translation>Les références dans groupes/capteurs/séquences devront être corrigées manuellement.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="329"/>
        <source>balanced</source>
        <translation>équilibrée</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="330"/>
        <source>fill</source>
        <translation>remplissage</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="341"/>
        <source>the group</source>
        <translation>le groupe</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="372"/>
        <source>the relay</source>
        <translation>le relais</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="461"/>
        <source>the sensor</source>
        <translation>le capteur</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="472"/>
        <location filename="../config_tab.py" line="488"/>
        <source>Converter</source>
        <translation>Convertisseur</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="473"/>
        <source>First select a sensor in the table.</source>
        <translation>Sélectionner d&apos;abord un capteur dans le tableau.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="488"/>
        <location filename="../config_tab.py" line="748"/>
        <source>Invalid parameters: {}</source>
        <translation>Paramètres invalides : {}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="590"/>
        <source>Cannot reload {}: {}</source>
        <translation>Rechargement impossible de {} : {}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="595"/>
        <source>Configuration loaded from {}.</source>
        <translation>Configuration chargée depuis {}.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="657"/>
        <source>✗ Invalid form/JSON: {}</source>
        <translation>✗ Formulaire/JSON invalide : {}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="663"/>
        <source>✓ Valid configuration.</source>
        <translation>✓ Configuration valide.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="684"/>
        <location filename="../config_tab.py" line="715"/>
        <source>Invalid configuration</source>
        <translation>Configuration invalide</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="693"/>
        <source>✓ Saved to {}.</source>
        <translation>✓ Enregistré dans {}.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="699"/>
        <source>Configuration</source>
        <translation>Configuration</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="700"/>
        <source>Stop the sequence before applying.</source>
        <translation>Arrêter la séquence avant d&apos;appliquer.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="705"/>
        <source>Apply</source>
        <translation>Appliquer</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="705"/>
        <source>The hardware will be switched off then reloaded.
Continue?</source>
        <translation>Le matériel va être coupé puis rechargé.
Continuer ?</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="738"/>
        <source>Configuration applied: {}</source>
        <translation>Configuration appliquée : {}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="748"/>
        <source>Assistant</source>
        <translation>Assistant</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="752"/>
        <source>Converter assistant</source>
        <translation>Assistant convertisseur</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="753"/>
        <source>&apos;converter&apos; block copied to the clipboard:

{}

Paste it into a sensor of the &apos;temperatures&apos; section (JSON).</source>
        <translation>Bloc &apos;converter&apos; copié dans le presse-papier :

{}

À coller dans un capteur de la section « températures » (JSON).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="759"/>
        <location filename="../config_tab.py" line="763"/>
        <location filename="../config_tab.py" line="786"/>
        <location filename="../config_tab.py" line="790"/>
        <source>Connection test</source>
        <translation>Test connexion</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="759"/>
        <source>SIMULATION mode: nothing to test.</source>
        <translation>Mode SIMULATION : rien à tester.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="764"/>
        <source>Select a supply in the table.</source>
        <translation>Sélectionner une alimentation dans le tableau.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="787"/>
        <source>{}: OK ✓

Model: {} ({} channels)
IDN: {}</source>
        <translation>{} : OK ✓

Modèle : {} ({} voies)
IDN : {}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="790"/>
        <source>{}: FAILURE

{}</source>
        <translation>{} : ÉCHEC

{}</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="797"/>
        <location filename="../config_tab.py" line="805"/>
        <location filename="../config_tab.py" line="820"/>
        <source>VISA scan</source>
        <translation>Scan VISA</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="797"/>
        <source>Unavailable in SIMULATION mode (simulate: true).</source>
        <translation>Indisponible en mode SIMULATION (simulate: true).</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="805"/>
        <source>No instrument found.</source>
        <translation>Aucun instrument trouvé.</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="807"/>
        <source>no IDN response</source>
        <translation>pas de réponse IDN</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="809"/>
        <source>Detected instruments</source>
        <translation>Instruments détectés</translation>
    </message>
    <message>
        <location filename="../config_tab.py" line="810"/>
        <source>Assign the resource to the selected channel:</source>
        <translation>Affecter la ressource à la voie sélectionnée :</translation>
    </message>
</context>
<context>
    <name>ConfigWizard</name>
    <message>
        <location filename="../config_wizard.py" line="54"/>
        <source>Configuration wizard</source>
        <translation>Assistant de configuration</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="63"/>
        <source>Welcome. This wizard prepares a starting configuration.&lt;br&gt;• &lt;b&gt;Without hardware&lt;/b&gt;: generate a &lt;b&gt;simulation&lt;/b&gt; configuration.&lt;br&gt;• &lt;b&gt;With hardware&lt;/b&gt;: &lt;b&gt;scan&lt;/b&gt; the connected VISA supplies, check the ones to include, then generate.</source>
        <translation>Bienvenue. Cet assistant prépare une configuration de départ.&lt;br&gt;• &lt;b&gt;Sans matériel&lt;/b&gt; : générez une configuration de &lt;b&gt;simulation&lt;/b&gt;.&lt;br&gt;• &lt;b&gt;Avec matériel&lt;/b&gt; : &lt;b&gt;scannez&lt;/b&gt; les alimentations VISA branchées, cochez celles à inclure, puis générez.</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="72"/>
        <source>🔎 Scan VISA hardware</source>
        <translation>🔎 Scanner le matériel VISA</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="73"/>
        <source>Detects USB-TMC and LAN VXI-11. An HMP in LAN socket mode (::5025::SOCKET) is NOT discoverable: use “Add a manual address”.</source>
        <translation>Détecte l&apos;USB-TMC et le LAN VXI-11. Un HMP en mode socket LAN (::5025::SOCKET) n&apos;est PAS découvrable : utiliser « Ajouter une adresse manuelle ».</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="78"/>
        <source>➕ Add a manual address…</source>
        <translation>➕ Ajouter une adresse manuelle…</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="79"/>
        <source>Enter and test a known VISA address (e.g. LAN socket TCPIP0::IP::5025::SOCKET).</source>
        <translation>Saisir et tester une adresse VISA connue (ex. socket LAN TCPIP0::IP::5025::SOCKET).</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="90"/>
        <source>Include</source>
        <translation>Inclure</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="90"/>
        <source>Name</source>
        <translation>Nom</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="90"/>
        <source>Model</source>
        <translation>Modèle</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="90"/>
        <source>VISA address (IDN)</source>
        <translation>Adresse VISA (IDN)</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="97"/>
        <source>Simulation configuration</source>
        <translation>Configuration de simulation</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="98"/>
        <source>Generates a config without hardware (one HMP4040, CH1/CH2).</source>
        <translation>Génère une config sans matériel (une HMP4040, CH1/CH2).</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="102"/>
        <source>Generate the configuration</source>
        <translation>Générer la configuration</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="107"/>
        <source>Cancel</source>
        <translation>Annuler</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="115"/>
        <source>Scanning… (a few seconds)</source>
        <translation>Scan en cours… (quelques secondes)</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="124"/>
        <source>Scan failed: {}</source>
        <translation>Scan impossible : {}</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="131"/>
        <source>{} instrument(s) detected.</source>
        <translation>{} instrument(s) détecté(s).</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="132"/>
        <source>No instrument detected — check wiring/VISA, or use simulation.</source>
        <translation>Aucun instrument détecté — vérifier câblage/VISA, ou utiliser la simulation.</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="145"/>
        <location filename="../config_wizard.py" line="170"/>
        <source>Add a manual address</source>
        <translation>Ajouter une adresse manuelle</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="146"/>
        <source>VISA address (e.g. LAN socket, USB):</source>
        <translation>Adresse VISA (ex. socket LAN, USB) :</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="152"/>
        <source>Testing {}…</source>
        <translation>Test de {}…</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="171"/>
        <source>No response from {}:
{}

Add this address anyway (to test later)?</source>
        <translation>Pas de réponse de {} :
{}

Ajouter quand même cette adresse (à tester plus tard) ?</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="177"/>
        <source>Address added without test: {}</source>
        <translation>Adresse ajoutée sans test : {}</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="220"/>
        <source>Wizard</source>
        <translation>Assistant</translation>
    </message>
    <message>
        <location filename="../config_wizard.py" line="220"/>
        <source>Check at least one supply to include.</source>
        <translation>Cochez au moins une alimentation à inclure.</translation>
    </message>
</context>
<context>
    <name>ConverterAssistant</name>
    <message>
        <location filename="../converter.py" line="111"/>
        <source>Temperature converter assistant</source>
        <translation>Assistant convertisseur de température</translation>
    </message>
    <message>
        <location filename="../converter.py" line="119"/>
        <source>Type</source>
        <translation>Type</translation>
    </message>
    <message>
        <location filename="../converter.py" line="146"/>
        <source>Copy the JSON</source>
        <translation>Copier le JSON</translation>
    </message>
    <message>
        <location filename="../converter.py" line="165"/>
        <source>Calibration points (voltage → °C)</source>
        <translation>Points d&apos;étalonnage (tension → °C)</translation>
    </message>
    <message>
        <location filename="../converter.py" line="168"/>
        <source>Voltage (V)</source>
        <translation>Tension (V)</translation>
    </message>
    <message>
        <location filename="../converter.py" line="173"/>
        <source>+ Point</source>
        <translation>+ Point</translation>
    </message>
    <message>
        <location filename="../converter.py" line="174"/>
        <source>− Point</source>
        <translation>− Point</translation>
    </message>
    <message>
        <location filename="../converter.py" line="175"/>
        <source>Import CSV…</source>
        <translation>Importer CSV…</translation>
    </message>
    <message>
        <location filename="../converter.py" line="182"/>
        <source>Parameters</source>
        <translation>Paramètres</translation>
    </message>
    <message>
        <location filename="../converter.py" line="187"/>
        <source>— preset —</source>
        <translation>— preset —</translation>
    </message>
    <message>
        <location filename="../converter.py" line="191"/>
        <source>Preset</source>
        <translation>Preset</translation>
    </message>
    <message>
        <location filename="../converter.py" line="227"/>
        <source>Import a calibration table</source>
        <translation>Importer une table d&apos;étalonnage</translation>
    </message>
    <message>
        <location filename="../converter.py" line="227"/>
        <source>CSV (*.csv *.txt);;All (*)</source>
        <translation>CSV (*.csv *.txt);;Tous (*)</translation>
    </message>
    <message>
        <location filename="../converter.py" line="233"/>
        <source>CSV import</source>
        <translation>Import CSV</translation>
    </message>
</context>
<context>
    <name>DividerSchematic</name>
    <message>
        <location filename="../converter.py" line="63"/>
        <source>Vref</source>
        <translation>Vréf</translation>
    </message>
    <message>
        <location filename="../converter.py" line="71"/>
        <source>→ ai (measured)</source>
        <translation>→ ai (mesure)</translation>
    </message>
</context>
<context>
    <name>EditorMixin</name>
    <message>
        <location filename="../editor.py" line="151"/>
        <source>channel V [I]</source>
        <translation>voie V [I]</translation>
    </message>
    <message>
        <location filename="../editor.py" line="172"/>
        <source>SET &lt;channel&gt; &lt;V&gt; &lt;I&gt;</source>
        <translation>SET &lt;voie&gt; &lt;V&gt; &lt;I&gt;</translation>
    </message>
    <message>
        <location filename="../editor.py" line="195"/>
        <source>Click a command to insert it at the cursor.</source>
        <translation>Cliquez une commande pour l'insérer au curseur.</translation>
    </message>
    <message>
        <location filename="../editor.py" line="196"/>
        <source>SERVO keys: step, min, max, tol, timeout, settle, invert (+ damping for ADAPT)&lt;br&gt;op: &amp;lt; &amp;lt;= &amp;gt; &amp;gt;= == !=&lt;br&gt;# or // : comment</source>
        <translation>clés SERVO : step, min, max, tol, timeout, settle, invert (+ damping pour ADAPT)&lt;br&gt;op : &amp;lt; &amp;lt;= &amp;gt; &amp;gt;= == !=&lt;br&gt;# ou // : commentaire</translation>
    </message>
    <message>
        <location filename="../editor.py" line="199"/>
        <source>Channels &amp;amp; groups</source>
        <translation>Voies &amp;amp; groupes</translation>
    </message>
    <message>
        <location filename="../editor.py" line="200"/>
        <source>Sensors</source>
        <translation>Capteurs</translation>
    </message>
    <message>
        <location filename="../editor.py" line="201"/>
        <source>Relays</source>
        <translation>Relais</translation>
    </message>
    <message>
        <location filename="../editor.py" line="228"/>
        <source>New</source>
        <translation>Nouveau</translation>
    </message>
    <message>
        <location filename="../editor.py" line="228"/>
        <source>Open…</source>
        <translation>Ouvrir…</translation>
    </message>
    <message>
        <location filename="../editor.py" line="229"/>
        <source>Save</source>
        <translation>Enregistrer</translation>
    </message>
    <message>
        <location filename="../editor.py" line="229"/>
        <source>Save as…</source>
        <translation>Enregistrer sous…</translation>
    </message>
    <message>
        <location filename="../editor.py" line="230"/>
        <source>Check</source>
        <translation>Vérifier</translation>
    </message>
    <message>
        <location filename="../editor.py" line="232"/>
        <source>▶ Load &amp; run</source>
        <translation>▶ Charger &amp; exécuter</translation>
    </message>
    <message>
        <location filename="../editor.py" line="347"/>
        <source>New sequence.</source>
        <translation>Nouvelle séquence.</translation>
    </message>
    <message>
        <location filename="../editor.py" line="353"/>
        <location filename="../editor.py" line="359"/>
        <source>Open a sequence</source>
        <translation>Ouvrir une séquence</translation>
    </message>
    <message>
        <location filename="../editor.py" line="353"/>
        <source>Sequence (*.seq *.txt);;All (*)</source>
        <translation>Séquence (*.seq *.txt);;Tous (*)</translation>
    </message>
    <message>
        <location filename="../editor.py" line="366"/>
        <source>Opened: {}</source>
        <translation>Ouvert : {}</translation>
    </message>
    <message>
        <location filename="../editor.py" line="384"/>
        <source>Saved: {}</source>
        <translation>Enregistré : {}</translation>
    </message>
    <message>
        <location filename="../editor.py" line="380"/>
        <location filename="../editor.py" line="391"/>
        <source>Save the sequence</source>
        <translation>Enregistrer la séquence</translation>
    </message>
    <message>
        <location filename="../editor.py" line="391"/>
        <source>Sequence (*.seq);;All (*)</source>
        <translation>Séquence (*.seq);;Tous (*)</translation>
    </message>
    <message>
        <location filename="../editor.py" line="417"/>
        <location filename="../editor.py" line="430"/>
        <source>, ~{:.0f}s min</source>
        <translation>, ~{:.0f}s mini</translation>
    </message>
    <message>
        <location filename="../editor.py" line="418"/>
        <location filename="../editor.py" line="431"/>
        <source>✓ Valid sequence ({} actions{}).</source>
        <translation>✓ Séquence valide ({} actions{}).</translation>
    </message>
</context>
<context>
    <name>RelayRowQt</name>
    <message>
        <location filename="../widgets.py" line="232"/>
        <source>Output</source>
        <translation>Sortie</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="233"/>
        <source>State</source>
        <translation>État</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="247"/>
        <location filename="../widgets.py" line="268"/>
        <source>OFF</source>
        <translation>OFF</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="261"/>
        <source>closed (ON)</source>
        <translation>fermé (ON)</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="263"/>
        <source>ON</source>
        <translation>ON</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="266"/>
        <source>open (OFF)</source>
        <translation>ouvert (OFF)</translation>
    </message>
</context>
<context>
    <name>SimMixin</name>
    <message>
        <location filename="../sim_tab.py" line="29"/>
        <source>&lt;b&gt;Simulation mode&lt;/b&gt; settings only, applied &lt;b&gt;live&lt;/b&gt;: the effect is visible immediately in the &lt;i&gt;Control&lt;/i&gt; tab (currents, temperature rise). They update the &lt;code&gt;simulation&lt;/code&gt; section of the in-memory configuration.</source>
        <translation>Réglages du &lt;b&gt;mode simulation&lt;/b&gt; uniquement, appliqués &lt;b&gt;en direct&lt;/b&gt; : l&apos;effet est visible immédiatement dans l&apos;onglet &lt;i&gt;Contrôle&lt;/i&gt; (courants, montée en température). Ils mettent à jour la section &lt;code&gt;simulation&lt;/code&gt; de la configuration en mémoire.</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="38"/>
        <source>Resistive loads per channel</source>
        <translation>Charges résistives par voie</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="40"/>
        <source>A load R sets the relation I = V/R (enters current limiting if V/R exceeds the limit).</source>
        <translation>Une charge R fixe la relation I = V/R (passage en limitation de courant si V/R dépasse la limite).</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="57"/>
        <source>Thermal model (simulated temperature rise)</source>
        <translation>Modèle thermique (montée en température simulée)</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="61"/>
        <source>Ambient</source>
        <translation>Ambiante</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="62"/>
        <source>Temperature at rest (zero power).</source>
        <translation>Température au repos (puissance nulle).</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="63"/>
        <source>Gain</source>
        <translation>Gain</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="64"/>
        <source>Rise per dissipated watt: target = ambient + gain × power.</source>
        <translation>Élévation par watt dissipé : cible = ambiante + gain × puissance.</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="65"/>
        <source>Time constant τ</source>
        <translation>Constante de temps τ</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="66"/>
        <source>Thermal response time (first-order response toward the target).</source>
        <translation>Temps de réponse thermique (réponse du 1er ordre vers la cible).</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="67"/>
        <source>Measurement noise</source>
        <translation>Bruit de mesure</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="68"/>
        <source>Amplitude of the noise added on each reading.</source>
        <translation>Amplitude du bruit ajouté à chaque lecture.</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="85"/>
        <source>Channel couplings (gate → drain)</source>
        <translation>Couplages entre voies (grille → drain)</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="88"/>
        <source>Models a transistor: the voltage of a &lt;b&gt;gate&lt;/b&gt; channel drives the current drawn on one or more &lt;b&gt;drain&lt;/b&gt; channels (Id = gm·(Vg − vth), capped at imax) — useful to test servo control (SERVO). Without coupling, each channel behaves as a plain resistive load (section above).</source>
        <translation>Modélise un transistor : la tension d&apos;une voie &lt;b&gt;grille&lt;/b&gt; pilote le courant tiré sur une ou plusieurs voies &lt;b&gt;drain&lt;/b&gt; (Id = gm·(Vg − vth), borné à imax) — utile pour tester l&apos;asservissement (SERVO). Sans couplage, chaque voie se comporte comme une simple charge résistive (section ci-dessus).</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="97"/>
        <source>Gate</source>
        <translation>Grille</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="97"/>
        <source>Drains (channels/groups, comma-separated)</source>
        <translation>Drains (voies/groupes, séparés par « , »)</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="104"/>
        <source>+ Add a coupling</source>
        <translation>+ Ajouter un couplage</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="106"/>
        <source>− Remove</source>
        <translation>− Supprimer</translation>
    </message>
    <message>
        <location filename="../sim_tab.py" line="129"/>
        <source>e.g. D1, D2  or  DRAIN</source>
        <translation>ex. D1, D2  ou  DRAIN</translation>
    </message>
</context>
<context>
    <name>TempRowQt</name>
    <message>
        <location filename="../widgets.py" line="291"/>
        <source>pending</source>
        <translation>en attente</translation>
    </message>
    <message>
        <location filename="../widgets.py" line="293"/>
        <source>FAULT</source>
        <translation>DÉFAUT</translation>
    </message>
</context>
<context>
    <name>plot</name>
    <message>
        <location filename="../plot.py" line="30"/>
        <location filename="../plot.py" line="271"/>
        <source>Voltage (V)</source>
        <translation>Tension (V)</translation>
    </message>
    <message>
        <location filename="../plot.py" line="31"/>
        <location filename="../plot.py" line="269"/>
        <source>Temperature (°C)</source>
        <translation>Température (°C)</translation>
    </message>
    <message>
        <location filename="../plot.py" line="166"/>
        <source>Waiting for data…</source>
        <translation>En attente de données…</translation>
    </message>
    <message>
        <location filename="../plot.py" line="270"/>
        <source>Current (A)</source>
        <translation>Courant (A)</translation>
    </message>
    <message>
        <location filename="../plot.py" line="432"/>
        <source>time (s) — window {} s</source>
        <translation>temps (s) — fenêtre {} s</translation>
    </message>
</context>
<context>
    <name>replay</name>
    <message>
        <location filename="../replay.py" line="132"/>
        <source>Temperatures (°C)</source>
        <translation>Températures (°C)</translation>
    </message>
    <message>
        <location filename="../replay.py" line="133"/>
        <source>Currents (A)</source>
        <translation>Courants (A)</translation>
    </message>
    <message>
        <location filename="../replay.py" line="134"/>
        <source>Voltages (V)</source>
        <translation>Tensions (V)</translation>
    </message>
    <message>
        <location filename="../replay.py" line="144"/>
        <source>operator {}</source>
        <translation>opérateur {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="146"/>
        <source>start {}</source>
        <translation>début {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="148"/>
        <source>end {}</source>
        <translation>fin {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="149"/>
        <source>mode {}</source>
        <translation>mode {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="150"/>
        <source>outcome: {}</source>
        <translation>issue : {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="156"/>
        <source>Events ({})</source>
        <translation>Événements ({})</translation>
    </message>
    <message>
        <location filename="../replay.py" line="183"/>
        <source>Replay — {}</source>
        <translation>Relecture — {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="195"/>
        <location filename="../replay.py" line="235"/>
        <source>Quantity:</source>
        <translation>Grandeur :</translation>
    </message>
    <message>
        <location filename="../replay.py" line="202"/>
        <source>📄 Generate the PDF report</source>
        <translation>📄 Générer le rapport PDF</translation>
    </message>
    <message>
        <location filename="../replay.py" line="221"/>
        <source>Comparison — {} vs {}</source>
        <translation>Comparaison — {} vs {}</translation>
    </message>
    <message>
        <location filename="../replay.py" line="226"/>
        <source>&lt;b&gt;A&lt;/b&gt; = {} &amp;nbsp;·&amp;nbsp; &lt;b&gt;B&lt;/b&gt; = {} &amp;nbsp;—&amp;nbsp; curves aligned on t = 0 (one color per series; click a legend entry to isolate it)</source>
        <translation>&lt;b&gt;A&lt;/b&gt; = {} &amp;nbsp;·&amp;nbsp; &lt;b&gt;B&lt;/b&gt; = {} &amp;nbsp;—&amp;nbsp; courbes recalées sur t = 0 (une couleur par série ; cliquer une entrée de légende pour l&apos;isoler)</translation>
    </message>
    <message>
        <location filename="../replay.py" line="251"/>
        <source>Export the chart</source>
        <translation>Exporter le graphe</translation>
    </message>
    <message>
        <location filename="../replay.py" line="251"/>
        <source>PNG image (*.png)</source>
        <translation>Image PNG (*.png)</translation>
    </message>
</context>
</TS>
