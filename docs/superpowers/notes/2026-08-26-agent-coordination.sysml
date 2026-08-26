// Reference model, non-binding — see 2026-08-26-subagent-dispatch-convention.md in this
// same directory for the naming/capability convention this model illustrates.
//
// Hand-authored (not generated) -- models this repo's own subagent-driven-development
// coordination structure: one Controller process dispatches fresh, isolated subagent
// processes that are cast into Implementer, Reviewer, or AdversarialReviewer roles for
// the duration of a single dispatch, then discarded.
//
// UFO framing: RustProcess is the rigid Kind -- a dispatched process IS a RustProcess
// for its entire lifetime, full stop, independent of any task. Controller, Implementer,
// Reviewer, and AdversarialReviewer are anti-rigid, relationally-dependent Roles: a
// process is a Reviewer only in relation to one active review context (dispatchContext
// below), and it stops being one the instant that context ends -- the very same
// RustProcess identity could be re-dispatched next as an Implementer without
// contradiction. `playedBy` on each Role part is that relational dependency made
// literal: a Role instance is nothing but a process-in-a-context, so it carries a
// reference to the process it is a Role *of*, rather than re-declaring processId or
// modelTier itself.
//
// Validated against the real sysml-v2-parser 0.54.0 grammar (the exact version
// rust/Cargo.lock pins for systhread-core) via a throwaway offline harness that
// reproduces systhread-core::validate::is_valid_sysml verbatim, sanity-checked first
// against a known-good repo fixture. Hand-authored text, not tool-generated -- kept
// here as a reference artifact, not wired into systhread's own render/check pipeline.

package AgentCoordination {
    part def RustProcess {
        attribute processId : String;
        attribute modelTier : String;
    }

    part def Controller {
        attribute playedBy : String;
        attribute capabilityTags : String;
        attribute dispatchBrief : String;
    }

    part def Implementer {
        attribute playedBy : String;
        attribute capabilityTags : String;
        attribute dispatchContext : String;
        attribute dispatchedBy : String;
        attribute deliverable : String;
    }

    part def Reviewer {
        attribute playedBy : String;
        attribute capabilityTags : String;
        attribute dispatchContext : String;
        attribute dispatchedBy : String;
        attribute reviewedDeliverable : String;
    }

    part def AdversarialReviewer {
        attribute playedBy : String;
        attribute capabilityTags : String;
        attribute dispatchContext : String;
        attribute dispatchedBy : String;
        attribute critiquedClaim : String;
    }

    part coordinationSession {
        part hostProcess_p0001 : RustProcess {
            attribute processId = "p0001";
            attribute modelTier = "opus";
        }

        part hostProcess_p0002 : RustProcess {
            attribute processId = "p0002";
            attribute modelTier = "sonnet";
        }

        part hostProcess_p0003 : RustProcess {
            attribute processId = "p0003";
            attribute modelTier = "sonnet";
        }

        part hostProcess_p0004 : RustProcess {
            attribute processId = "p0004";
            attribute modelTier = "sonnet";
        }

        part hostProcess_p0005 : RustProcess {
            attribute processId = "p0005";
            attribute modelTier = "opus";
        }

        part controller : Controller {
            attribute playedBy = "p0001";
            attribute capabilityTags = "dispatch, plan-synthesis, task-scoping, result-integration";
            attribute dispatchBrief = "hand-author and validate an AgentCoordination SysML v2 model of this repo's own subagent-driven-development structure";
        }

        part implementer_sysmlAuthoring : Implementer {
            attribute playedBy = "p0002";
            attribute capabilityTags = "read, write, edit, bash";
            attribute dispatchContext = "hand-author AgentCoordination.sysml against sysml_gen.rs conventions";
            attribute dispatchedBy = "controller";
            attribute deliverable = "AgentCoordination.sysml";
        }

        part implementer_validateHarness : Implementer {
            attribute playedBy = "p0003";
            attribute capabilityTags = "bash, cargo-build, cargo-run";
            attribute dispatchContext = "stand up an offline throwaway crate against sysml-v2-parser 0.54.0 to check the model actually parses";
            attribute dispatchedBy = "controller";
            attribute deliverable = "ferris-validate scratch crate";
        }

        part reviewer_syntaxCheck : Reviewer {
            attribute playedBy = "p0004";
            attribute capabilityTags = "read, bash";
            attribute dispatchContext = "confirm AgentCoordination.sysml matches sysml_gen.rs indentation and attribute conventions";
            attribute dispatchedBy = "controller";
            attribute reviewedDeliverable = "AgentCoordination.sysml";
        }

        part adversarialReviewer_ufoFraming : AdversarialReviewer {
            attribute playedBy = "p0005";
            attribute capabilityTags = "read, critique";
            attribute dispatchContext = "stress-test the Role/Kind UFO framing before it is trusted in the report";
            attribute dispatchedBy = "controller";
            attribute critiquedClaim = "RustProcess is a rigid Kind and Controller, Implementer, Reviewer, AdversarialReviewer are anti-rigid, relationally dependent Roles played by it for the duration of one dispatch";
        }
    }
}
