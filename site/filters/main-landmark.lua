-- Wrap each page's content in one main landmark.
-- Quarto's custom page layout (used site-wide) emits no <main>. A wrapper Div keeps
-- the nesting valid around Pandoc's <section> elements, and its id is the one
-- Quarto's "Skip to main content" link targets.
function Pandoc(doc)
  if not quarto.doc.is_format("html") then
    return doc
  end
  local attr = pandoc.Attr("quarto-document-content", { "content" }, { role = "main" })
  doc.blocks = pandoc.Blocks({ pandoc.Div(doc.blocks, attr) })
  return doc
end
