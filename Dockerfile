# c411-autodl : image légère, sans aucune dépendance Python externe
FROM python:3.13-slim

LABEL org.opencontainers.image.title="c411-autodl" \
      org.opencontainers.image.description="Ajoute automatiquement dans qBittorrent les nouveaux torrents c411 selon tes critères, en protégeant ton ratio" \
      org.opencontainers.image.source="https://github.com/Xeerac/c411-autodl" \
      org.opencontainers.image.licenses="MIT"

# Fuseaux horaires : nécessaires pour que BILAN_HEURE corresponde à ton heure locale (TZ)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

# Le programme ne tourne pas en root
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin autodl

WORKDIR /app
COPY c411_autodl.py ./
COPY autodl/ ./autodl/
RUN mkdir -p /app/donnees && chown autodl:autodl /app/donnees

ENV PYTHONUNBUFFERED=1 \
    TZ=Europe/Paris

USER autodl

# Historique des ajouts, suivi et journal : à monter pour qu'ils survivent aux mises à jour
VOLUME ["/app/donnees"]

# La configuration est lue dans /app/.env (à monter en lecture seule)
ENTRYPOINT ["python", "/app/c411_autodl.py"]
CMD ["--boucle", "300"]
