import { Button } from "@/components/ui/button";
import { AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription, AlertDialogFooter, AlertDialogCancel, AlertDialogAction } from "@/components/ui/alert-dialog";

interface Props { open: boolean; saving: boolean; onCancel: () => void; onDiscard: () => void; onSave: () => void; }
export default function UnsavedScoringDialog({ open, saving, onCancel, onDiscard, onSave }: Props) {
  return (
        <AlertDialog open={open} onOpenChange={(open) => { if (!open) onCancel(); }}>
          <AlertDialogContent data-testid="unsaved-changes-dialog">
            <AlertDialogHeader>
              <AlertDialogTitle>Unsaved Changes</AlertDialogTitle>
              <AlertDialogDescription>
                Your scoring format change hasn't been saved yet. Would you like to save before leaving?
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter className="gap-2 sm:gap-0">
              <AlertDialogCancel
                onClick={onCancel}
                data-testid="unsaved-changes-cancel-btn"
              >
                Stay
              </AlertDialogCancel>
              <Button
                variant="outline"
                onClick={onDiscard}
                data-testid="unsaved-changes-discard-btn"
              >
                Discard & Leave
              </Button>
              <AlertDialogAction
                onClick={onSave}
                disabled={saving}
                data-testid="unsaved-changes-save-btn"
              >
                {saving ? "Saving…" : "Save & Leave"}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
  );
}
