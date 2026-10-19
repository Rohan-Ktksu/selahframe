"use strict";

const $ = id => document.getElementById(id);
const base = "/api/projects";
const views = ["passage", "narration", "scenes", "audio", "export"];
const state = {
  project: null, projects: [], health: null, exports: [], view: "narration",
  scriptVersion: null, scriptDirty: false, scenes: [], sceneRevision: null,
  sceneSaved: "", sceneDirty: false, narrationMs: null, music: null,
  musicRevision: null, musicDirty: false, pending: new Set(), load: 0,
  polling: false, previewFailed: null, toastTimer: null,
};

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.classList.add("icon");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", "#icon-" + name);
  svg.appendChild(use);
  return svg;
}

function route(suffix = "") {
  if (!state.project) throw Error("Open or create a project first.");
  return `${base}/${encodeURIComponent(state.project.id)}${suffix}`;
}

async function api(path, method = "GET", data = null) {
  const options = {method};
  if (data instanceof FormData) options.body = data;
  else if (data !== null) {
    options.headers = {"Content-Type": "application/json"};
    options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options);
  let body;
  try { body = await response.json(); } catch { body = {}; }
  if (!response.ok) {
    let detail = body.detail;
    if (Array.isArray(detail)) detail = detail.map(item => item.msg).join(". ");
    throw Error(typeof detail === "string" ? detail : `Request failed (${response.status}). Please try again.`);
  }
  return body;
}

function notify(message, error = false) {
  clearTimeout(state.toastTimer);
  $("toastMessage").textContent = message;
  $("toast").classList.toggle("error", error);
  $("toast").setAttribute("role", error ? "alert" : "status");
  $("toast").hidden = false;
  if (!error) state.toastTimer = setTimeout(() => { $("toast").hidden = true; }, 5500);
}

async function perform(key, task, success) {
  if (state.pending.has(key)) return;
  state.pending.add(key);
  if (changingProject() || key === "create") state.load += 1;
  syncControls();
  try {
    const result = await task();
    if (success) notify(success);
    return result;
  } catch (error) {
    notify(error.message || "Could not connect. Check that SelahFrame is running.", true);
    if (key === "create") {
      $("createError").textContent = error.message;
      $("createError").hidden = false;
    }
  } finally {
    state.pending.delete(key);
    syncControls();
  }
}

function hasChanges() { return state.scriptDirty || state.sceneDirty || state.musicDirty; }
function changingProject() { return ["script", "approve", "draft", "scenes", "music", "image", "import", "render", "drive", "cinematic"].some(key => state.pending.has(key)); }
function isBusy() { return ["rendering", "uploading", "importing_music", "generating_images"].includes(state.project?.status); }
function isApproved() { return !!state.project?.approved_version && state.project.approved_version === state.project.script_version; }
function mediaReady() { return ["ffmpeg", "ffprobe", "piper", "voice_model"].every(key => state.health?.components[key]); }
function seconds(ms) { return (ms / 1000).toFixed(1) + "s"; }
function sceneEdits() { return state.scenes.map(({id, enabled, duration_weight, motion_style}) => ({id, enabled, duration_weight: Number(duration_weight), motion_style})); }
function musicEdits() { return {asset_id: $("musicTrack").value || null, enabled: $("musicEnabled").checked, gain_db: Number($("musicGain").value)}; }

function badgeStatus(status) {
  return ({draft: "Draft", review: "Needs review", approved: "Script approved", complete: "Video ready",
    failed: "Needs attention", rendering: "Rendering", uploading: "Archiving", importing_music: "Importing music", generating_images: "Creating images"})[status] || "Draft";
}

function showLibrary() {
  document.title = "Projects · SelahFrame";
  $("libraryView").hidden = false;
  $("studioView").hidden = true;
  $("projectsNav").setAttribute("aria-current", "page");
  $("studioNav").removeAttribute("aria-current");
  const url = new URL(location.href);
  url.searchParams.delete("project");
  url.hash = "";
  history.replaceState(null, "", url);
}

function showView(view = state.view, focus = false) {
  if (!state.project) { showLibrary(); return; }
  document.title = state.project.title + " · SelahFrame";
  state.view = views.includes(view) ? view : "narration";
  $("libraryView").hidden = true;
  $("studioView").hidden = false;
  $("studioNav").setAttribute("aria-current", "page");
  $("projectsNav").removeAttribute("aria-current");
  views.forEach(name => {
    const active = name === state.view;
    $("tab-" + name).setAttribute("aria-selected", String(active));
    $("tab-" + name).tabIndex = active ? 0 : -1;
    $("panel-" + name).hidden = !active;
  });
  if (focus) $("tab-" + state.view).focus();
  const url = new URL(location.href);
  url.searchParams.set("project", state.project.id);
  url.hash = state.view;
  history.replaceState(null, "", url);
  if (state.view === "narration") resizeScript();
}

function resizeScript() {
  const area = $("narration");
  if ($("panel-narration").hidden) return;
  area.style.height = "auto";
  area.style.height = Math.min(Math.max(area.scrollHeight + 2, 230), 740) + "px";
}

async function listProjects() {
  state.projects = await api(base);
  drawProjects();
}

function drawProjects() {
  const query = $("projectSearch").value.trim().toLocaleLowerCase();
  const rows = state.projects.filter(project => `${project.title} ${project.reference}`.toLocaleLowerCase().includes(query));
  const box = $("projects");
  box.replaceChildren();
  $("projectCount").textContent = state.projects.length;
  $("emptyProjects").hidden = rows.length > 0;
  $("emptyProjects").querySelector("h2").textContent = state.projects.length ? "No matching projects." : "Your next story starts here.";
  $("emptyProjects").querySelector("p").textContent = state.projects.length ? "Try another project name or passage reference." : "Add a verified passage, write your narration, and make it your own.";
  $("emptyCreate").textContent = state.projects.length ? "Create a new project" : "Create your first project";
  rows.forEach(project => {
    const card = element("article", "project-card");
    const art = element("div", "project-art");
    art.appendChild(element("span", "", project.reference));
    const body = element("div", "project-card-body");
    body.appendChild(element("h3", "", project.title));
    const date = new Date(project.created_at.replace(" ", "T") + "Z");
    body.appendChild(element("p", "project-card-meta", `${project.translation || "Verified passage"} · ${Number.isNaN(date.valueOf()) ? "Saved project" : date.toLocaleDateString("en-IN", {day: "numeric", month: "short"})}`));
    const footer = element("div", "project-card-footer");
    footer.appendChild(element("span", "badge" + (project.status === "failed" ? " error" : " subtle"), badgeStatus(project.status)));
    const open = element("button", "text-button", "Open project");
    open.type = "button";
    open.dataset.openProject = project.id;
    open.setAttribute("aria-label", "Open " + project.title);
    open.appendChild(icon("arrow"));
    open.addEventListener("click", () => perform("open", () => openProject(project.id)));
    footer.appendChild(open);
    body.appendChild(footer);
    card.append(art, body);
    box.appendChild(card);
  });
}

async function openProject(id, view = "narration", force = false) {
  if (!force && changingProject()) throw Error("Wait for the current change to finish before switching projects.");
  if (!force && state.project?.id !== id && hasChanges()) throw Error("Save or reload your unsaved edits before switching projects.");
  const ticket = ++state.load;
  const path = `${base}/${encodeURIComponent(id)}`;
  const [project, scenes, music, exports] = await Promise.all([api(path), api(path + "/scenes"), api(path + "/music"), api(path + "/exports")]);
  if (ticket !== state.load) return;
  state.project = project;
  state.exports = exports;
  state.previewFailed = null;
  state.scriptVersion = project.script_version;
  state.scriptDirty = false;
  $("narration").value = project.script;
  applyScenePlan(scenes);
  applyMusicPlan(music);
  paintProject();
  showView(view);
  window.scrollTo({top: 0, behavior: "auto"});
}

function paintProject() {
  const project = state.project;
  if (!project) return;
  if ($("libraryView").hidden) document.title = project.title + " · SelahFrame";
  const labels = {projectHeading: project.title, projectReference: project.reference,
    projectTranslation: project.translation, passageReference: project.reference,
    passageTranslation: project.translation, passageText: project.scripture,
    passageSource: project.scripture_source, passageLicense: project.source_license,
    passageContext: project.context_text, projectId: project.id,
    detailVersion: project.script_version ? `Version ${project.script_version}` : "Not saved yet",
    posterTitle: project.title, posterReference: project.reference};
  Object.entries(labels).forEach(([id, text]) => { $(id).textContent = text; });
  $("projectStatus").textContent = badgeStatus(project.status);
  $("projectStatus").className = "badge" + (project.status === "failed" ? " error" : "");
  $("projectError").textContent = project.error;
  $("projectError").hidden = !project.error;
  paintScript();
  syncPreview();
  syncControls();
}

function paintScript() {
  const project = state.project;
  if (!project) return;
  const words = $("narration").value.trim().split(/\s+/).filter(Boolean).length;
  $("wordCount").textContent = `${words} ${words === 1 ? "word" : "words"}`;
  $("scriptVersion").textContent = state.scriptDirty ? "Unsaved edits" : project.script_version ? `Version ${project.script_version}` : "No saved version";
  $("narrationBadge").textContent = state.scriptDirty ? "Unsaved edits" : isApproved() ? "Approved" : "Ready for review";
  $("narrationBadge").className = "badge" + (state.scriptDirty ? " warning" : " subtle");
  $("saveState").textContent = hasChanges() ? "Unsaved changes" : "All changes saved";
  $("narrationHint").textContent = state.scriptDirty ? "Save this draft before approving or rendering it." : isApproved() ? `Version ${project.approved_version} is approved. Editing the narration will require a new approval.` : "Save your edits, then approve the exact narration you want in the video.";
}

function applyScenePlan(plan) {
  state.sceneRevision = plan.image_revision;
  state.scenes = plan.scenes;
  state.narrationMs = plan.narration_duration_ms;
  state.sceneSaved = JSON.stringify(sceneEdits());
  state.sceneDirty = false;
  drawScenes();
  $("sceneNotice").textContent = state.scenes.length ? "Time weights share the full narration. Original images are kept when excluded." : "Add your first image to start a scene plan.";
  $("sceneNotice").classList.remove("unsaved");
  $("imageUploadPanel").open = !state.scenes.length;
}

function drawScenes() {
  const box = $("sceneList");
  box.replaceChildren();
  state.scenes.forEach((scene, index) => {
    const card = element("article", "scene-card" + (scene.enabled ? "" : " excluded"));
    card.id = "scene-" + scene.id;
    const top = element("div", "scene-card-top");
    const thumb = element("div", "scene-thumbnail");
    const image = element("img");
    image.src = scene.thumbnail_url;
    image.alt = scene.placeholder ? "Abstract placeholder" : `${scene.generated ? "AI-generated" : "Uploaded"} scene ${index + 1}`;
    image.loading = "lazy";
    thumb.append(image, element("span", "scene-number", String(index + 1).padStart(2, "0")));
    const settings = element("div", "scene-settings");
    const heading = element("h3", "", `Scene ${index + 1}`);
    if (scene.placeholder || scene.generated) heading.appendChild(element("span", "placeholder-tag", scene.placeholder ? "Abstract" : "AI generated"));
    const motionLabel = element("label", "", "Camera movement");
    const motion = element("select");
    motion.setAttribute("aria-label", `Scene ${index + 1} motion`);
    [["zoom_in", "Slow zoom in"], ["zoom_out", "Slow zoom out"], ["still", "Still image"]].forEach(([value, text]) => {
      const option = element("option", "", text); option.value = value; motion.appendChild(option);
    });
    motion.value = scene.motion_style;
    motion.addEventListener("change", () => { scene.motion_style = motion.value; sceneChanged(); });
    motionLabel.appendChild(motion);
    const weightLabel = element("label", "scene-weight", "Time weight");
    const weight = element("input");
    Object.assign(weight, {type: "number", min: "0.25", max: "10", step: "0.25", value: scene.duration_weight});
    weight.setAttribute("aria-label", `Scene ${index + 1} time weight`);
    weight.addEventListener("input", () => { scene.duration_weight = weight.value; sceneChanged(); });
    weightLabel.appendChild(weight);
    settings.append(heading, motionLabel, weightLabel);
    top.append(thumb, settings);
    const footer = element("div", "scene-card-footer");
    const includeLabel = element("label", "check-row");
    const include = element("input"); include.type = "checkbox"; include.checked = scene.enabled;
    include.setAttribute("aria-label", `Include scene ${index + 1}`);
    include.addEventListener("change", () => { scene.enabled = include.checked; card.classList.toggle("excluded", !scene.enabled); sceneChanged(); });
    includeLabel.append(include, element("span", "", "In video"));
    footer.appendChild(includeLabel);
    [[-1, "up", "earlier"], [1, "down", "later"]].forEach(([direction, name, label]) => {
      const button = element("button", "icon-button"); button.type = "button";
      button.setAttribute("aria-label", `Move scene ${index + 1} ${label}`);
      button.disabled = index + direction < 0 || index + direction >= state.scenes.length;
      button.appendChild(icon(name));
      button.addEventListener("click", () => {
        [state.scenes[index], state.scenes[index + direction]] = [state.scenes[index + direction], state.scenes[index]];
        drawScenes(); sceneChanged();
      });
      footer.appendChild(button);
    });
    const share = element("p", "scene-share"); share.dataset.sceneShare = scene.id;
    const rights = element("details", "scene-rights");
    rights.append(element("summary", "", "Source & rights"), element("p", "", `${scene.source_url} · ${scene.license_name}`));
    card.append(top, footer, share, rights);
    box.appendChild(card);
  });
  paintSceneShares();
  drawSequence();
}

function paintSceneShares() {
  const total = state.scenes.filter(scene => scene.enabled).reduce((n, scene) => n + Number(scene.duration_weight || 0), 0);
  document.querySelectorAll("[data-scene-share]").forEach(node => {
    const scene = state.scenes.find(item => item.id === node.dataset.sceneShare);
    const share = scene.enabled && total ? Number(scene.duration_weight) / total : 0;
    node.textContent = !scene.enabled ? "Excluded from the next render" : `${(share * 100).toFixed(1)}% of narration${state.narrationMs ? ` · about ${seconds(state.narrationMs * share)}` : ""}`;
  });
}

function sceneChanged() {
  state.sceneDirty = JSON.stringify(sceneEdits()) !== state.sceneSaved;
  $("sceneNotice").textContent = state.sceneDirty ? "Unsaved scene changes. Save your plan before rendering." : "Your scene plan matches the saved version.";
  $("sceneNotice").classList.toggle("unsaved", state.sceneDirty);
  paintSceneShares(); drawSequence(); paintScript(); syncPreview(); syncControls();
}

function drawSequence() {
  const included = state.scenes.filter(scene => scene.enabled);
  const total = included.reduce((n, scene) => n + Number(scene.duration_weight || 0), 0);
  $("sceneCount").textContent = included.length;
  $("sequenceMeta").textContent = `${included.length} ${included.length === 1 ? "scene" : "scenes"}${state.narrationMs ? " · " + seconds(state.narrationMs) + " narration" : " · Timing after first render"}`;
  const strip = $("sequenceStrip"); strip.replaceChildren();
  if (!state.scenes.length) strip.appendChild(element("p", "sequence-empty", "Add images in Scenes, or start a project with the abstract pack."));
  state.scenes.forEach((scene, index) => {
    const button = element("button", "sequence-item" + (scene.enabled ? "" : " excluded"));
    button.type = "button";
    button.setAttribute("aria-label", `Edit scene ${index + 1}${scene.enabled ? "" : ", excluded"}`);
    const img = element("img"); img.src = scene.thumbnail_url; img.alt = ""; img.loading = "lazy";
    const label = element("span", "sequence-label", `Scene ${index + 1}`);
    label.appendChild(element("span", "", !scene.enabled ? "Excluded" : state.narrationMs && total ? "~" + seconds(state.narrationMs * Number(scene.duration_weight) / total) : "Weight " + scene.duration_weight));
    button.append(img, label);
    button.addEventListener("click", () => { showView("scenes"); $("scene-" + scene.id)?.scrollIntoView({block: "center", behavior: "smooth"}); });
    strip.appendChild(button);
  });
}

function applyMusicPlan(plan) {
  state.music = plan; state.musicRevision = plan.music_revision; state.musicDirty = false;
  const select = $("musicTrack"); select.replaceChildren();
  const none = element("option", "", "No track selected"); none.value = ""; select.appendChild(none);
  plan.tracks.forEach(track => { const option = element("option", "", track.name); option.value = track.id; select.appendChild(option); });
  select.value = plan.asset_id || "";
  $("musicEnabled").checked = plan.enabled; $("musicGain").value = plan.gain_db;
  $("musicUploadPanel").open = !plan.tracks.length;
  paintMusic();
}

function paintMusic() {
  const track = state.music?.tracks.find(item => item.id === $("musicTrack").value);
  const audio = $("musicPreview");
  audio.hidden = !track;
  audio.volume = Math.min(0.25, 10 ** (Number($("musicGain").value) / 20));
  if (track) {
    if (audio.getAttribute("src") !== track.preview_url) { audio.pause(); audio.src = track.preview_url; }
    $("musicAttribution").textContent = `${seconds(track.duration_ms)} · Source: ${track.source_url} · Rights: ${track.license_name}`;
  } else {
    audio.pause(); audio.removeAttribute("src");
    $("musicAttribution").textContent = "Import a track below to add music to your video.";
  }
  $("musicGainLabel").textContent = $("musicGain").value + " dB below voice";
  $("audioBadge").textContent = $("musicEnabled").checked ? "Music on" : "Music off";
  $("sequenceMusic").textContent = state.musicDirty ? "Unsaved audio changes" : state.music?.enabled ? "Background music on" : "Music off";
  $("musicNotice").textContent = state.musicDirty ? "Unsaved audio changes. Save before rendering." : state.music?.enabled ? "Music is enabled for your next render." : "Music is off. Your next render uses narration only.";
  $("musicNotice").classList.toggle("unsaved", state.musicDirty);
}

function musicChanged() {
  const saved = state.music;
  state.musicDirty = !!saved && JSON.stringify(musicEdits()) !== JSON.stringify({asset_id: saved.asset_id, enabled: saved.enabled, gain_db: saved.gain_db});
  paintMusic(); paintScript(); syncPreview(); syncControls();
}

function syncPreview() {
  const project = state.project;
  if (!project) return;
  const ready = ["complete", "uploading"].includes(project.status);
  const latest = state.exports.find(item => item.id === project.job?.id) || state.exports[0];
  const video = $("preview");
  const source = `${base}/${encodeURIComponent(project.id)}/preview?v=${latest?.id || project.script_version}`;
  video.hidden = !ready || state.previewFailed === source;
  $("previewPlaceholder").hidden = !video.hidden;
  if (ready && video.getAttribute("src") !== source) { state.previewFailed = null; video.src = source; }
  if (!ready && video.getAttribute("src")) { video.pause(); video.removeAttribute("src"); video.load(); }
  const first = state.scenes.find(scene => scene.enabled);
  $("previewImage").hidden = !first;
  $("previewLandscape").hidden = !!first;
  if (first) { $("previewImage").src = first.thumbnail_url; $("previewImage").alt = first.placeholder ? "Abstract placeholder scene" : "First included scene image"; }
  $("download").hidden = !ready;
  if (ready) $("download").href = `${base}/${encodeURIComponent(project.id)}/download`;
  else $("download").removeAttribute("href");
  $("previewQuality").textContent = ready && latest ? `${latest.width} × ${latest.height}` : "Scene preview";
  $("previewDuration").textContent = ready && latest ? seconds(latest.duration_ms) : "";
  $("previewHint").textContent = state.previewFailed === source ? "The preview could not play. Download the video to review it in your media player." : ready ? hasChanges() ? "Latest saved render. Save and render again to apply your edits." : "Your latest rendered video. Take a moment to review it." : isBusy() ? "Your video will appear here when the render is complete." : "Render to hear the narration and see the captions.";
  const active = isBusy() && project.job?.status === "running";
  $("jobCard").hidden = !active;
  if (active) {
    const labels = {preflight: "Preparing your video", voice: "Creating narration", scenes: "Building scenes", captions: "Adding captions", verify: "Checking your export", "music-mix": "Mixing the soundtrack", "music-import": "Preparing your track", drive: "Archiving to Drive", "drive-verify": "Verifying the archive"};
    $("stage").textContent = labels[project.job.stage] || (project.job.stage.startsWith("Images") ? project.job.stage : "Working on your project");
    $("progress").value = project.job.progress;
    $("progressValue").textContent = project.job.progress + "%";
  }
}

function syncControls() {
  const project = state.project, busy = isBusy(), pending = state.pending;
  $("exportNav").disabled = !project;
  $("studioNav").disabled = !project;
  $("newProjectFields").disabled = pending.has("create");
  ["newProject", "libraryCreate", "emptyCreate"].forEach(id => { $(id).disabled = changingProject() || pending.has("open") || pending.has("create"); });
  document.querySelectorAll("[data-open-project]").forEach(button => { button.disabled = pending.has("open") || changingProject(); });
  if (!project) return;
  const switching = pending.has("open") || pending.has("create");
  $("narration").readOnly = busy || switching || pending.has("script") || pending.has("approve");
  $("sceneControls").disabled = busy || switching || pending.has("scenes") || pending.has("image");
  $("imageControls").disabled = busy || switching || pending.has("image");
  $("musicControls").disabled = busy || switching || pending.has("music") || pending.has("import");
  $("musicImportControls").disabled = busy || switching || pending.has("music") || pending.has("import");
  $("saveScript").disabled = busy || pending.has("script") || !state.scriptDirty || $("narration").value.trim().length < 10;
  $("approveScript").disabled = busy || pending.has("approve") || state.scriptDirty || !project.script_version || isApproved();
  $("generateDraft").disabled = busy || pending.has("draft") || !state.health?.components.ollama;
  $("generateDraft").textContent = pending.has("draft") ? "Generating…" : "Generate draft";
  $("reloadScript").disabled = busy || pending.has("script");
  $("saveScenes").disabled = busy || pending.has("scenes") || !state.sceneDirty;
  $("reloadScenes").disabled = busy || pending.has("scenes");
  $("saveMusic").disabled = busy || pending.has("music") || !state.musicDirty;
  $("reloadMusic").disabled = busy || pending.has("music");
  $("uploadImage").disabled = pending.has("image");
  $("importMusic").disabled = pending.has("import") || (state.music?.tracks.length || 0) >= 3;
  const validScenes = state.scenes.some(scene => scene.enabled);
  const canRender = !busy && !changingProject() && !hasChanges() && isApproved() && validScenes && mediaReady();
  $("renderVideo").disabled = !canRender || pending.has("render");
  $("quality").disabled = busy;
  $("cinematicControls").disabled = busy || switching || pending.has("cinematic");
  $("generateImages").disabled = busy || hasChanges() || pending.has("cinematic");
  $("cancelImages").hidden = project.status !== "generating_images";
  $("cancelImages").disabled = pending.has("cancelImages");
  $("cinematicRender").disabled = !isApproved() || state.scriptDirty;
  if (!isApproved()) $("cinematicRender").checked = false;
  $("cinematicText").textContent = $("cinematicSource").value === "verse" ? project.scripture : project.script || "Save narration first.";
  $("cinematicHint").textContent = hasChanges() ? "Save your edits before generating images." : "No payment or personal API key required. No paid fallback. Each image may take up to 10 minutes.";

  $("renderHint").textContent = busy ? "A job is already running. Your progress is shown beside the preview." : hasChanges() ? "Save all edits before rendering. Narration changes also need your approval." : !isApproved() ? "Review and approve your saved narration to continue." : !validScenes ? "Include at least one scene in your video." : !mediaReady() ? "Local video tools need setup. Check Project details below." : "Everything is ready. Render the saved project when you’re happy with it.";
  const checks = [[true, "Verified passage recorded", "passage"], [isApproved() && !state.scriptDirty, "Narration approved", "narration"], [validScenes && !state.sceneDirty, "Scene plan saved", "scenes"]];
  if (state.music?.enabled || state.musicDirty) checks.push([!state.musicDirty, "Music settings saved", "audio"]);
  const box = $("renderChecklist"); box.replaceChildren();
  checks.forEach(([complete, label, view]) => {
    const row = element("div", "checklist-row" + (complete ? " complete" : ""));
    const mark = element("span", "check-mark"); if (complete) mark.appendChild(icon("check"));
    row.append(mark, element("span", "", label));
    if (!complete) { const edit = element("button", "text-button", "Review"); edit.type = "button"; edit.addEventListener("click", () => showView(view)); row.appendChild(edit); }
    box.appendChild(row);
  });
  $("uploadDrive").disabled = busy || changingProject() || project.status !== "complete" || hasChanges() || !state.health?.components.rclone;
  $("driveHint").textContent = state.health?.components.rclone ? "Archive your finished export to your configured Google Drive." : "Connect Google Drive with rclone to enable archiving. Local exports work without it.";
  $("driveStatus").textContent = project.drive_status === "verified-size" ? "Archive verified by file name and size. Local files are retained." : project.drive_status === "failed" ? "The archive did not finish. Your local files are retained." : "";
}

async function refreshProject(force = false) {
  if (!state.project || state.pending.has("open") || state.pending.has("create") || (!force && changingProject())) return;
  if (state.polling) {
    if (!force) return;
    await state.polling;
  }
  const request = pollProject();
  state.polling = request;
  try { await request; } finally { if (state.polling === request) state.polling = null; }
}

async function pollProject() {
  const id = state.project.id, ticket = state.load;
  try {
    const project = await api(`${base}/${encodeURIComponent(id)}`);
    if (ticket !== state.load || state.project.id !== id) return;
    const previous = state.project;
    state.project = project;
    if (!state.scriptDirty && project.script_version !== state.scriptVersion) {
      $("narration").value = project.script; state.scriptVersion = project.script_version;
      resizeScript();
    }
    const completed = project.status === "complete" && previous.status !== "complete";
    if (!state.sceneDirty && (project.image_revision !== state.sceneRevision || completed)) {
      const plan = await api(route("/scenes"));
      if (ticket !== state.load || state.sceneDirty) return;
      applyScenePlan(plan);
    }
    if (!state.musicDirty && project.music_revision !== state.musicRevision) {
      const plan = await api(route("/music"));
      if (ticket !== state.load || state.musicDirty) return;
      applyMusicPlan(plan);
    }
    if (completed || project.job?.id !== previous.job?.id) {
      const exports = await api(route("/exports"));
      if (ticket !== state.load) return;
      state.exports = exports;
    }
    paintProject();
  } catch {
    if (ticket === state.load) $("saveState").textContent = "Connection lost · reconnecting…";
  }
}

function openNewProject() {
  if (changingProject()) { notify("Wait for the current change to finish first.", true); return; }
  if (hasChanges()) { notify("Save or reload your current edits before starting another project.", true); return; }
  $("createError").hidden = true;
  $("newProjectDialog").showModal();
}

async function createProject() {
  const names = ["title", "reference", "scripture", "translation", "scripture_source", "source_license", "context_text"];
  if (names.some(name => !$(name).value.trim())) throw Error("Fill in the project, passage, source and context fields.");
  const payload = Object.fromEntries(names.map(name => [name, $(name).value]));
  payload.placeholders = $("placeholders").checked;
  const project = await api(base, "POST", payload);
  await openProject(project.id, "narration", true);
  $("newProjectDialog").close(); $("newProjectForm").reset();
  await listProjects();
}

async function saveScript() {
  const id = state.project.id, text = $("narration").value;
  const current = await api(route());
  if (current.script_version !== state.scriptVersion) throw Error("Another narration version was saved. Keep a copy of your edits before reloading the saved script.");
  const project = await api(route("/script"), "PUT", {script: text});
  if (state.project.id !== id) return;
  state.project = project; state.scriptVersion = project.script_version;
  state.scriptDirty = $("narration").value !== project.script;
  paintProject(); resizeScript();
}

async function approveScript() {
  const current = await api(route());
  if (current.script !== $("narration").value || current.script_version !== state.scriptVersion) throw Error("Save or reload the current narration before approving it.");
  state.project = await api(route("/approve"), "POST", {script_version: state.scriptVersion});
  paintProject();
}

async function generateDraft() {
  if (state.scriptDirty) throw Error("Save your narration edits before generating a draft.");
  const text = $("narration").value, id = state.project.id;
  const project = await api(route("/generate-script"), "POST");
  if (state.project.id !== id) return;
  state.project = project; state.scriptVersion = project.script_version;
  if ($("narration").value === text) $("narration").value = project.script;
  else notify("The generated draft was saved. Your unsaved narration is still in the editor.");
  state.scriptDirty = $("narration").value !== project.script;
  paintProject();
}

async function saveScenes() {
  const edits = sceneEdits();
  if (!edits.some(scene => scene.enabled)) throw Error("Include at least one scene in the video.");
  if (edits.some(scene => !Number.isFinite(scene.duration_weight) || scene.duration_weight < 0.25 || scene.duration_weight > 10)) throw Error("Time weights must be between 0.25 and 10.");
  const path = route("/scenes");
  await api(path, "PUT", {image_revision: state.sceneRevision, scenes: edits});
  applyScenePlan(await api(path));
  await refreshProject(true);
}

async function uploadImage() {
  if (state.sceneDirty) throw Error("Save or reload your scene edits before adding an image.");
  const file = $("image").files[0]; if (!file) throw Error("Choose an image first.");
  const form = new FormData(); form.append("image", file);
  form.append("source_url", $("image_source").value); form.append("license_name", $("image_license").value);
  await api(route("/images"), "POST", form);
  $("image").value = "";
  applyScenePlan(await api(route("/scenes")));
  await refreshProject(true);
}

async function saveMusic() {
  await api(route("/music"), "PUT", {music_revision: state.musicRevision, ...musicEdits()});
  applyMusicPlan(await api(route("/music")));
  await refreshProject(true);
}

async function importMusic() {
  if (state.musicDirty) throw Error("Save or reload your music settings before importing another track.");
  const file = $("musicFile").files[0]; if (!file) throw Error("Choose a music track first.");
  if (file.size > (state.health?.max_music_mb || 25) * 1024 * 1024) throw Error("Choose a smaller track within the displayed file limit.");
  if (!$("musicRights").checked) throw Error("Confirm your permission to use this track.");
  const form = new FormData(); form.append("track", file);
  form.append("source_url", $("musicSource").value); form.append("license_name", $("musicLicense").value); form.append("rights_confirmed", "true");
  await api(route("/music/tracks"), "POST", form);
  $("musicFile").value = ""; $("musicRights").checked = false;
  await refreshProject(true);
}

async function renderVideo() {
  if (hasChanges()) throw Error("Save your edits before rendering.");
  const current = await api(route());
  if (current.script !== $("narration").value) throw Error("Save and approve the current narration first.");
  const result = await api(route("/render"), "POST", {quality: $("quality").value});
  if (result.status === "complete") notify("The current saved export is ready to download.");
  await refreshProject(true);
}

async function uploadDrive() {
  if (hasChanges()) throw Error("Save and render your edits before archiving.");
  const current = await api(route());
  if (current.script !== $("narration").value) throw Error("Save, approve and render your narration before archiving.");
  await api(route("/upload-drive"), "POST");
  await refreshProject(true);
}

async function generateImages() {
  if (hasChanges()) throw Error("Save all edits before generating images.");
  if (!$("cinematicConsent").checked) throw Error("Confirm sending the selected text to AI Horde first.");
  await api(route("/cinematic"), "POST", {
    source: $("cinematicSource").value, count: Number($("cinematicCount").value),
    direction: $("cinematicDirection").value, image_revision: state.sceneRevision,
    script_version: state.scriptVersion, consent: true, replace_plan: $("cinematicReplace").checked,
    render_after: $("cinematicRender").checked, quality: $("quality").value,
  });
  $("cinematicConsent").checked = false;
  await refreshProject(true);
}

async function loadHealth() {
  state.health = await api("/api/health");
  const missing = ["ffmpeg", "ffprobe", "piper", "voice_model"].filter(key => !state.health.components[key]);
  $("readiness").textContent = missing.length ? "Setup needed: " + missing.join(", ") : "Local voice and video tools ready";
  $("draftingNote").textContent = state.health.components.ollama ? "Optional AI drafts need your review before approval." : "Write your narration here. AI drafting is available when Ollama is installed.";
  $("musicLimits").textContent = `WAV, MP3 or FLAC · up to ${state.health.max_music_mb} MB and 5 minutes`;
  syncControls();
}

$("brandHome").addEventListener("click", showLibrary);
$("projectsNav").addEventListener("click", () => { showLibrary(); perform("list", listProjects); });
$("backProjects").addEventListener("click", () => { showLibrary(); perform("list", listProjects); });
$("studioNav").addEventListener("click", () => showView());
$("exportNav").addEventListener("click", () => showView("export"));
["newProject", "libraryCreate", "emptyCreate"].forEach(id => $(id).addEventListener("click", openNewProject));
["closeNewProject", "cancelNewProject"].forEach(id => $(id).addEventListener("click", () => $("newProjectDialog").close()));
$("newProjectForm").addEventListener("submit", event => { event.preventDefault(); perform("create", createProject, "Project created. Your narration is ready to write."); });
$("projectSearch").addEventListener("input", drawProjects);
$("refreshProjects").addEventListener("click", () => perform("list", listProjects));
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => showView(button.dataset.view)));
document.querySelectorAll("[data-go]").forEach(button => button.addEventListener("click", () => showView(button.dataset.go, true)));
$("workflowTabs").addEventListener("keydown", event => {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  const current = views.indexOf(state.view);
  const next = event.key === "Home" ? 0 : event.key === "End" ? views.length - 1 : (current + (event.key === "ArrowRight" ? 1 : -1) + views.length) % views.length;
  showView(views[next], true);
});
$("narration").addEventListener("input", () => { state.scriptDirty = $("narration").value !== state.project?.script; resizeScript(); paintScript(); syncControls(); syncPreview(); });
$("saveScript").addEventListener("click", () => perform("script", saveScript, "Narration saved. Review it before approving."));
$("approveScript").addEventListener("click", () => perform("approve", approveScript, "Script approved for your next render."));
$("generateDraft").addEventListener("click", () => perform("draft", generateDraft));
$("reloadScript").addEventListener("click", () => perform("script", async () => {
  const project = await api(route()); state.project = project; state.scriptVersion = project.script_version;
  $("narration").value = project.script; state.scriptDirty = false; resizeScript(); paintProject();
}, "Saved narration restored."));
$("saveScenes").addEventListener("click", () => perform("scenes", saveScenes, "Scene plan saved. Render to apply it."));
$("reloadScenes").addEventListener("click", () => perform("scenes", async () => { applyScenePlan(await api(route("/scenes"))); await refreshProject(true); }));
$("imageForm").addEventListener("submit", event => { event.preventDefault(); perform("image", uploadImage, "Image added to your scene plan."); });
["musicTrack", "musicEnabled"].forEach(id => $(id).addEventListener("change", musicChanged));
$("cinematicForm").addEventListener("submit", event => { event.preventDefault(); perform("cinematic", generateImages, "Image generation started. You can follow the queue beside the preview."); });
$("cinematicSource").addEventListener("change", syncControls);
$("cancelImages").addEventListener("click", () => perform("cancelImages", async () => { await api(route("/cinematic/cancel"), "POST"); await refreshProject(true); }, "Image generation cancelled. Your previous scene plan is retained."));
$("musicGain").addEventListener("input", musicChanged);
$("saveMusic").addEventListener("click", () => perform("music", saveMusic, "Music settings saved. Render to apply them."));
$("reloadMusic").addEventListener("click", () => perform("music", async () => { applyMusicPlan(await api(route("/music"))); await refreshProject(true); }));
$("musicForm").addEventListener("submit", event => { event.preventDefault(); perform("import", importMusic, "Music import started. Your track will be available shortly."); });
$("renderVideo").addEventListener("click", () => perform("render", renderVideo));
$("uploadDrive").addEventListener("click", () => perform("drive", uploadDrive));
$("checkStatus").addEventListener("click", () => perform("refresh", refreshProject));
$("editSequence").addEventListener("click", () => showView("scenes", true));
$("dismissToast").addEventListener("click", () => { $("toast").hidden = true; });
$("preview").addEventListener("error", () => { if ($("preview").getAttribute("src")) { state.previewFailed = $("preview").getAttribute("src"); syncPreview(); } });
document.querySelectorAll(".icon,.section-icon").forEach(svg => { svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false"); });
window.addEventListener("beforeunload", event => { if (hasChanges()) { event.preventDefault(); event.returnValue = ""; } });
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshProject(); });
window.addEventListener("resize", resizeScript);
setInterval(() => { if (!document.hidden) refreshProject(); }, 3000);
perform("list", listProjects);
perform("health", loadHealth);
const selected = new URLSearchParams(location.search).get("project");
if (selected) {
  const legacy = {sceneEditor: "scenes", musicEditor: "audio"};
  const view = location.hash.slice(1);
  perform("open", () => openProject(selected, legacy[view] || view || "narration"));
} else showLibrary();
