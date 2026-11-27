-- Language plumbing in every page's <head>:
--   * <link rel="alternate" hreflang> for each language in `site-langs` (_quarto.yml),
--     plus x-default (the first language). `href` is absolute, for search engines;
--     `data-href` is the same page relative to this one, for the switch and detection,
--     so they also work on a local preview.
--   * lang-detect.js (first visit: a Turkish-preferring browser goes to Turkish once),
--     inlined after the links it reads, so it runs before the page paints.
--   * #site-strings: the profile's `site-strings` as JSON, for site.js.
-- The 404 page gets only the strings: GitHub Pages serves it at any missing URL, so it
-- has no fixed counterpart (404.qmd works out its language from the URL).

local function plain(value)
  local kind = pandoc.utils.type(value)
  if kind == "boolean" or kind == "number" then
    return value
  elseif kind == "List" then
    local out = {}
    for i, item in ipairs(value) do
      out[i] = plain(item)
    end
    return out
  elseif kind == "table" then
    local out = {}
    for k, item in pairs(value) do
      out[k] = plain(item)
    end
    return out
  end
  return pandoc.utils.stringify(value)
end

local function attr(s)
  return (s:gsub("&", "&amp;"):gsub('"', "&quot;"):gsub("<", "&lt;"))
end

local function read_file(name)
  local f = assert(io.open(quarto.utils.resolve_path(name), "r"))
  local text = f:read("a")
  f:close()
  return text
end

-- This page's path in its tree ("hazelnut/analyses/exports.html").
local function page_path()
  local dir = quarto.project.directory:gsub("\\", "/"):gsub("/$", "")
  local file = quarto.doc.input_file:gsub("\\", "/")
  if file:sub(1, #dir + 1) ~= dir .. "/" then
    return nil
  end
  return (file:sub(#dir + 2):gsub("%.qmd$", ".html"))
end

-- "a/b/" -> "../../"
local function up(path)
  local _, n = path:gsub("/", "")
  return string.rep("../", n)
end

local function hreflang_links(langs, current, rel)
  local default_url = langs[1].url
  local trees = {} -- each language's tree under the default one ("" / "tr/")
  for _, l in ipairs(langs) do
    if l.url:sub(1, #default_url) ~= default_url then
      error("site-langs: " .. l.url .. " is not under " .. default_url)
    end
    trees[l.lang] = l.url:sub(#default_url + 1)
  end
  if trees[current] == nil then
    error("site-langs has no entry for lang " .. current)
  end
  -- From this page up to the default tree's root.
  local to_root = up(rel) .. up(trees[current])
  local out = {}
  local function link(hreflang, l)
    out[#out + 1] = string.format('<link rel="alternate" hreflang="%s" href="%s" data-href="%s">',
      hreflang, attr(l.url .. rel), attr(to_root .. trees[l.lang] .. rel))
  end
  for _, l in ipairs(langs) do
    link(l.lang, l)
  end
  link("x-default", langs[1])
  return table.concat(out, "\n")
end

function Meta(meta)
  if not quarto.doc.is_format("html") then
    return nil
  end
  if meta["site-strings"] ~= nil then
    local json = quarto.json.encode(plain(meta["site-strings"])):gsub("</", "<\\/")
    quarto.doc.include_text("in-header",
      '<script type="application/json" id="site-strings">' .. json .. "</script>")
  end
  local rel = page_path()
  if meta["site-langs"] == nil or rel == nil or rel == "404.html" then
    return nil
  end
  local langs = plain(meta["site-langs"])
  quarto.doc.include_text("in-header", hreflang_links(langs, pandoc.utils.stringify(meta.lang), rel))
  quarto.doc.include_text("in-header", "<script>\n" .. read_file("lang-detect.js") .. "</script>")
  return nil
end
