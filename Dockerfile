# Apify actor image with Python 3.14 and Playwright + Chromium preinstalled.
FROM apify/actor-python-playwright:3.14

WORKDIR /usr/src/app

# Install Python dependencies (the `apify` SDK ships in the base image;
# pinning it here keeps a known-good version).
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# CloakBrowser manages its own patched Chromium. Bake it into the image at
# build time so containers start instantly instead of downloading ~150 MB
# on every run.
ENV CLOAKBROWSER_CACHE_DIR=/opt/cloakbrowser
RUN python -c "from cloakbrowser.download import ensure_binary; ensure_binary()" \
    && du -sh /opt/cloakbrowser

COPY . ./

# The scraper writes output/, cache/ and profiles/ under the workdir, and
# CloakBrowser needs to read (and sometimes refresh) its binary cache in
# /opt/cloakbrowser at runtime. The base image defines a dedicated non-root
# user (myuser, whose home is symlinked to /usr/src/app); grant it ownership
# of every runtime-writable path so the container never runs as root.
RUN mkdir -p output cache profiles /opt/cloakbrowser \
    && chown -R myuser:myuser /usr/src/app /opt/cloakbrowser

USER myuser

# Launch the actor package module.
CMD ["python", "-m", "src"]