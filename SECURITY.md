# Politique de sécurité

## ⚠️ Avertissement de sûreté (à lire)

ALIM_SEQ pilote des **alimentations de puissance** sur du matériel réel. Ses
protections — coupure thermique, arrêts ordonnés, arrêt d'urgence — sont
**logicielles**. Elles **ne remplacent pas** un dispositif de sûreté **matériel**
(interlock, fusible, limiteur) ni le jugement de l'opérateur.

Le logiciel est fourni **sans aucune garantie** (licence GNU GPL-3.0), **n'est pas
certifié** pour un usage critique, et son utilisation se fait **à vos propres
risques**. Vérifiez toujours l'aire de sécurité (SOA), le câblage et la tenue en
tension de votre montage.

**Réseau.** Le protocole SCPI/TCPIP est **sans authentification** : tout hôte du
réseau peut piloter les instruments. Raccordez le matériel sur un **réseau de banc
isolé** (VLAN ou segment dédié), jamais exposé au réseau bureautique ou à Internet.

## Versions supportées

Seule la **dernière version** publiée reçoit des correctifs.

| Version | Supportée |
|---|---|
| dernière (`main`) | ✅ |
| antérieures | ❌ |

## Signaler une vulnérabilité

Merci de **ne pas** ouvrir d'issue publique pour une faille de sécurité.

Utilisez la fonction **« Report a vulnerability »** (onglet *Security* → *Advisories*)
du dépôt GitHub, qui ouvre un canal **privé** avec les mainteneurs. Décrivez :

- le composant concerné et la version,
- les étapes de reproduction,
- l'impact potentiel (sûreté matérielle, exécution, fuite d'information).

Une réponse est visée sous **quelques jours ouvrés**. Merci de laisser un délai
raisonnable de correction avant toute divulgation publique.
