import React, { useState, useRef, useEffect } from "react";
import { FileText, Upload, Trash2, Search, MessageSquare } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { useToast } from "@/hooks/use-toast";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Document } from "@/api/types/document";
import { documentService } from "@/api/services/document.service";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";


const DocumentsPage: React.FC = () => {
  const [documents, setDocuments] = useState<Document[]>([]);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { toast } = useToast();

  useEffect(() => {
    let isMounted = true;

    const fetchDocuments = async () => {
      try {
        const response = await documentService.getDocuments();
        if (!response) {
          throw new Error(`Failed to fetch documents`);
        }

        const data = response.documents;
        setDocuments(data);
      } catch (error) {
        const message = error instanceof Error ? error.message : "Unknown error";
        toast({
          title: "Unable to load documents",
          description: message,
          variant: "destructive",
        });
      }
    };

    fetchDocuments();

    return () => {
      isMounted = false;
    };
  }, [toast]);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = event.target.files;
    if (!files || files.length === 0) {
      return;
    }

    const formData = new FormData();
    Array.from(files).forEach((file) => {
      formData.append("files", file);
    });

    try {
      const response = await documentService.uploadFile(formData);
      const uploadedDocuments = response.documents;
      setDocuments((prevDocs) => [...prevDocs, ...uploadedDocuments]);
      toast({
        title: "Upload Successful",
        description: `${files.length} document${files.length > 1 ? "s" : ""} uploaded.`,
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      toast({
        title: "Upload Failed",
        description: message,
        variant: "destructive",
      });
    } finally {
      event.target.value = "";
    }
  };

  const handleStartChat = (documentId: string, documentName: string) => {
    navigate(`/chat/${documentId}`, { state: { documentName } });
  };

  const handleDelete = async (documentId: string) => {
    try {
      const isSuccess = await documentService.deleteDocument(documentId);
      if (!isSuccess) {
        throw new Error(`Failed to delete document with id: ${documentId}`);
      }
      setDocuments((prevDocs) => prevDocs.filter((doc) => doc._id !== documentId));
      toast({
        title: "Document Deleted",
        description: "The document has been successfully deleted.",
        variant: "destructive",
      });
    } catch (error) {
      toast({
        title: "Document Deletion Failed",
        description: "An error occurred while deleting the document.",
        variant: "destructive",
      });
    }
  };

  const filteredDocuments = documents.filter((doc) =>
    doc.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-bold">Documents</h1>

      <div className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            type="text"
            placeholder="Search documents..."
            className="pl-9"
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
        <label htmlFor="file-upload" className="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground hover:bg-primary/90 h-10 px-4 py-2 cursor-pointer">
          <Upload className="mr-2 h-4 w-4" /> Upload Document
          <Input id="file-upload" type="file" className="sr-only" onChange={handleFileChange} multiple />
        </label>
      </div>

      <div className="rounded-md border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Uploaded At</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredDocuments.length > 0 ? (
              filteredDocuments.map((doc) => (
                <TableRow key={doc._id}>
                  <TableCell className="font-medium flex items-center gap-2">
                    <FileText className="h-4 w-4 text-muted-foreground" />
                    {doc.name}
                  </TableCell>
                  <TableCell>{doc.created_at}</TableCell>
                  <TableCell className="text-right flex gap-2 justify-end"> {/* Added flex and gap for buttons */}
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleStartChat(doc._id, doc.name)}
                    >
                      <MessageSquare className="h-4 w-4 mr-2" />
                      Chat
                    </Button>
                    <AlertDialog>
                      <AlertDialogTrigger asChild>
                        <Button variant="destructive" size="sm">
                          <Trash2 className="h-4 w-4" />
                          <span className="sr-only">Delete</span>
                        </Button>
                      </AlertDialogTrigger>
                      <AlertDialogContent>
                        <AlertDialogHeader>
                          <AlertDialogTitle>Are you absolutely sure?</AlertDialogTitle>
                          <AlertDialogDescription>
                            This action cannot be undone. This will permanently delete the document
                            <span className="font-bold"> "{doc.name}"</span>.
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>Cancel</AlertDialogCancel>
                          <AlertDialogAction onClick={() => handleDelete(doc._id)}>Continue</AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </TableCell>
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell colSpan={4} className="h-24 text-center text-muted-foreground">
                  No documents found.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
};

export default DocumentsPage;