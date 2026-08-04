const regionForm = document.querySelector("#region-form");
const queryInput = document.querySelector("#region-query");
const regionResults = document.querySelector("#region-results");
const searchFeedback = document.querySelector("#search-feedback");
const readingFeedback = document.querySelector("#reading-feedback");
const readingSection = document.querySelector("#reading");
const readingLoader = document.querySelector("#reading-loader");
const radiusInput = document.querySelector("#radius");
const radiusOutput = document.querySelector("#radius-output");
const systemState = document.querySelector("#system-state");
const systemStateWrap = document.querySelector(".system-state");

const readingTitle = document.querySelector("#reading-title");
const temperatureValue = document.querySelector("#temperature-value");
const temperatureUnit = document.querySelector("#temperature-unit");
const temperatureStatus = document.querySelector("#temperature-status");
const sensorCount = document.querySelector("#sensor-count");
const selectedRadius = document.querySelector("#selected-radius");
const observationTime = document.querySelector("#observation-time");
const cacheBadge = document.querySelector("#cache-badge");
let temperatureRequestController = null;

radiusInput.addEventListener("input", () => {
  radiusOutput.value = `${radiusInput.value} km`;
});

async function readJson(response) {
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error?.message || "The request could not be completed");
  }
  return payload;
}

async function checkHealth() {
  try {
    const response = await fetch("/healthz", { headers: { Accept: "application/json" } });
    await readJson(response);
    systemState.textContent = "API online";
    systemStateWrap.classList.add("online");
  } catch (_error) {
    systemState.textContent = "API unavailable";
    systemStateWrap.classList.remove("online");
  }
}

function setFeedback(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle("error", isError);
}

function setReadingLoading(isLoading) {
  readingSection.classList.toggle("is-loading", isLoading);
  readingSection.setAttribute("aria-busy", String(isLoading));
  readingLoader.hidden = !isLoading;
}

function renderRegions(results) {
  regionResults.replaceChildren();
  if (results.length === 0) {
    setFeedback(searchFeedback, "No matching regions were found. Try a nearby city.", true);
    return;
  }

  results.forEach((region) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "region-result";

    const label = document.createElement("span");
    const name = document.createElement("strong");
    const meta = document.createElement("small");
    name.textContent = region.display_name;
    meta.textContent = [region.type, region.country_code].filter(Boolean).join(" · ");
    label.append(name, meta);

    const arrow = document.createElement("span");
    arrow.textContent = "→";
    arrow.setAttribute("aria-hidden", "true");
    button.append(label, arrow);
    button.addEventListener("click", () => loadTemperature(region));
    regionResults.append(button);
  });
}

async function loadTemperature(region) {
  temperatureRequestController?.abort();
  const requestController = new AbortController();
  temperatureRequestController = requestController;
  const radius = Number(radiusInput.value);
  const parameters = new URLSearchParams({
    lat: region.lat,
    lon: region.lon,
    radius_km: radius,
    name: region.display_name,
  });
  if (Array.isArray(region.bbox) && region.bbox.length === 4) {
    parameters.set("bbox", region.bbox.join(","));
  }

  setFeedback(readingFeedback, "");
  setReadingLoading(true);
  cacheBadge.hidden = true;
  readingTitle.textContent = region.display_name;
  document.querySelector("#reading").scrollIntoView({ behavior: "smooth", block: "start" });

  try {
    const response = await fetch(`/api/temperature?${parameters}`, {
      headers: { Accept: "application/json" },
      signal: requestController.signal,
    });
    const reading = await readJson(response);
    temperatureValue.textContent = Number(reading.average_temperature).toFixed(1);
    temperatureUnit.textContent = reading.unit;
    temperatureStatus.textContent = reading.status;
    sensorCount.textContent = reading.active_sensors_calculated;
    selectedRadius.textContent = reading.region?.area_mode ? "Region area" : `${radius} km`;
    observationTime.textContent = reading.latest_observation_at
      ? `Latest sensor update ${new Date(reading.latest_observation_at).toLocaleString()}`
      : "Measurements from the past hour";
    cacheBadge.hidden = false;
    cacheBadge.textContent = reading.cached ? "Valkey cache" : "Fresh fetch";
    setFeedback(
      readingFeedback,
      `${reading.measurements_considered} measurements checked · source: ${reading.source}`,
    );
  } catch (error) {
    if (error.name === "AbortError") return;
    temperatureValue.textContent = "—";
    sensorCount.textContent = "—";
    cacheBadge.hidden = true;
    setFeedback(readingFeedback, error.message, true);
  } finally {
    if (temperatureRequestController === requestController) {
      temperatureRequestController = null;
      setReadingLoading(false);
    }
  }
}

regionForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  regionResults.replaceChildren();
  setFeedback(searchFeedback, "Searching OpenStreetMap…");

  try {
    const parameters = new URLSearchParams({ q: queryInput.value.trim() });
    const response = await fetch(`/api/regions/search?${parameters}`, {
      headers: { Accept: "application/json" },
    });
    const payload = await readJson(response);
    setFeedback(
      searchFeedback,
      payload.cached ? "Loaded from the location cache." : "Choose one matching region.",
    );
    renderRegions(payload.results);
  } catch (error) {
    setFeedback(searchFeedback, error.message, true);
  }
});

checkHealth();
