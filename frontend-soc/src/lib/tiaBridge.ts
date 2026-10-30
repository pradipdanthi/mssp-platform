import { ackUiCommand } from "../api/soc";
import { alertDetailPath } from "./socPaths";
import { tiaSessionId } from "./tiaSession";
import { createUiBridge } from "./uiBridge";

/** The one dashboard command bridge for this browser tab. */
export const uiBridge = createUiBridge({
  ack: (commandId, body) => ackUiCommand(commandId, { session_id: tiaSessionId(), ...body }),
  detailPath: alertDetailPath,
});
