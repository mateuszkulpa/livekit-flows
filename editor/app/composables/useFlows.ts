import { computed } from 'vue'
import { useStorage } from '@vueuse/core'
import YAML from 'yaml'
import type { ConversationFlow, FlowNode, NodePositionMap } from '@/types/flow'
import { welcomeFlow, welcomeFlowPositions } from './welcomeFlow'

type FlowRecord = ConversationFlow & { id: string, name: string }

const FLOWS_KEY = 'flows'
const POSITIONS_KEY = 'positions'
const ACTIVE_ID_KEY = 'activeFlowId'

export function useFlows() {
  const flows = useStorage<FlowRecord[]>(FLOWS_KEY, [])
  const positionsByFlowId = useStorage<Record<string, NodePositionMap>>(POSITIONS_KEY, {})
  const activeFlowId = useStorage<string | null>(ACTIVE_ID_KEY, null)

  const activeFlow = computed(() => flows.value.find(f => f.id === activeFlowId.value) || null)
  const activePositions = computed<NodePositionMap>(() => (activeFlowId.value ? positionsByFlowId.value[activeFlowId.value] || {} : {}))

  if (flows.value.length === 0) {
    createWelcomeFlow()
  }

  function generateId(prefix: string) {
    return `${prefix}-${Math.random().toString(36).slice(2, 8)}${Date.now().toString(36).slice(-3)}`
  }

  async function createWelcomeFlow() {
    const id = generateId('flow')
    flows.value.push({ ...welcomeFlow, id, name: 'Welcome Example' })
    positionsByFlowId.value[id] = { ...welcomeFlowPositions }
    activeFlowId.value = id
  }

  function createFlow(name = 'Untitled Flow') {
    const id = generateId('flow')
    const base: ConversationFlow = {
      system_prompt: '',
      initial_node: 'node-1',
      nodes: [{ id: 'node-1', name: 'Start', is_final: false, edges: [] }],
      actions: [],
      environment_variables: {},
    }
    flows.value.push({ ...base, id, name })
    positionsByFlowId.value[id] = { 'node-1': { x: 200, y: 160 } }
    activeFlowId.value = id
  }

  function selectFlow(id: string) {
    activeFlowId.value = id
  }

  function renameFlow(id: string, name: string) {
    const f = flows.value.find(f => f.id === id)
    if (f) f.name = name
  }

  function duplicateFlow(id: string) {
    const s = flows.value.find(f => f.id === id)
    if (!s) return
    const nid = generateId('flow')
    flows.value.push({ ...structuredClone(s), id: nid, name: `${s.name} (copy)` })
    positionsByFlowId.value[nid] = structuredClone(positionsByFlowId.value[id] || {})
    activeFlowId.value = nid
  }

  function deleteFlow(id: string) {
    const i = flows.value.findIndex(f => f.id === id)
    if (i !== -1) flows.value.splice(i, 1)
    positionsByFlowId.value[id] = {}
    if (activeFlowId.value === id) activeFlowId.value = flows.value[0]?.id || null
  }

  function updateActiveFlow(mutator: (flow: FlowRecord) => void) {
    const f = activeFlow.value
    if (!f) return
    mutator(f)
  }

  function setPositions(flowId: string, positions: NodePositionMap) {
    positionsByFlowId.value[flowId] = positions
  }

  function updatePosition(nodeId: string, pos: { x: number, y: number }) {
    if (!activeFlowId.value) return
    const currentMap = positionsByFlowId.value[activeFlowId.value] || {}
    positionsByFlowId.value[activeFlowId.value] = { ...currentMap, [nodeId]: pos }
  }

  function addNode(position?: { x: number, y: number }) {
    if (!activeFlowId.value) return
    const flow = activeFlow.value
    if (!flow) return

    const nodeId = `node-${Date.now()}`
    const defaultPosition = position || { x: 200, y: 200 }

    const newNode: FlowNode = {
      id: nodeId,
      name: 'New Node',
      instruction: '',
      static_text: '',
      is_final: false,
      edges: [],
      actions: [],
    }

    flow.nodes.push(newNode)
    const currentMap = positionsByFlowId.value[activeFlowId.value] || {}
    positionsByFlowId.value[activeFlowId.value] = { ...currentMap, [nodeId]: defaultPosition }
  }

  function deleteNode(nodeId: string) {
    if (!activeFlowId.value) return
    const flow = activeFlow.value
    if (!flow) return

    if (flow.nodes.length <= 1) return
    if (nodeId === flow.initial_node) return

    const nodeIndex = flow.nodes.findIndex(node => node.id === nodeId)
    if (nodeIndex !== -1) {
      flow.nodes.splice(nodeIndex, 1)
    }

    flow.nodes.forEach((node) => {
      node.edges = node.edges?.filter(edge => edge.target_node_id !== nodeId) || []
    })

    const currentMap = positionsByFlowId.value[activeFlowId.value] || {}
    const { [nodeId]: deleted, ...newMap } = currentMap
    positionsByFlowId.value[activeFlowId.value] = newMap
  }

  async function importFlowFromFile(file: File) {
    const text = await file.text()
    const isYaml = /\.(yaml|yml)$/i.test(file.name) || /^[\s\S]*:\s*[\s\S]*$/m.test(text)
    const data = isYaml ? YAML.parse(text) : JSON.parse(text)
    const id = generateId('flow')
    const name = file.name.replace(/\.(json|ya?ml)$/i, '')
    flows.value.push({ ...data, id, name })
    positionsByFlowId.value[id] = {}
    activeFlowId.value = id
  }

  return {
    flows,
    activeFlowId,
    activeFlow,
    activePositions,
    createFlow,
    selectFlow,
    renameFlow,
    duplicateFlow,
    deleteFlow,
    updateActiveFlow,
    setPositions,
    updatePosition,
    addNode,
    deleteNode,
    importFlowFromFile,
  }
}
