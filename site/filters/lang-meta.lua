-- Per-language page metadata: on the Turkish profile, a page's `title-tr` and
-- `description-tr` replace its `title` and `description` (the <title>, the meta
-- description and the title block). English pages are left as they are.
local function profile_active(name)
  for _, p in ipairs(quarto.project.profile or {}) do
    if p == name then
      return true
    end
  end
  return false
end

function Meta(meta)
  if not profile_active("tr") then
    return nil
  end
  for _, key in ipairs({ "title", "description" }) do
    if meta[key .. "-tr"] ~= nil then
      meta[key] = meta[key .. "-tr"]
    end
  end
  return meta
end
